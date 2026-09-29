"""
app.py  — KnapResume Local Flask server (python app.py → http://localhost:5000)
For GitHub Pages deployment, see docs/index.html + .github/workflows/deploy.yml
"""

import os, sys, uuid, threading, re, time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template_string, abort
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from src.logger import get_logger
from src.parser import extract_text
from src.web_context import fetch_company_context
from src.tailor import tailor_resume, generate_cover_letter
from src.pdf_generator import generate_resume_pdf, generate_cover_letter_pdf
from src.database import init_db
from src import profile_service as ps
from src.profile_service import ProfileNotFoundError, FactNotFoundError

logger = get_logger("app")

try:
    init_db()
except Exception as e:
    logger.warning("DB init skipped: %s", e)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
OUTPUT_DIR = Path("outputs"); OUTPUT_DIR.mkdir(exist_ok=True)
jobs: dict = {}

ENV_ANTHROPIC = os.environ.get("ANTHROPIC_API_KEY", "")
ENV_GEMINI    = os.environ.get("GEMINI_API_KEY", "")

# ── HTML ──────────────────────────────────────────────────────────────────────
with open(Path(__file__).parent / "docs" / "index.html", encoding="utf-8") as f:
    _TEMPLATE = f.read()

@app.route("/")
def index():
    logger.debug("Serving index.html")
    html = _TEMPLATE \
        .replace("__ANTHROPIC_KEY__", ENV_ANTHROPIC or "") \
        .replace("__GEMINI_KEY__",    ENV_GEMINI    or "") \
        .replace("__GITHUB_PAGES__",  "false")
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}

# ── API ───────────────────────────────────────────────────────────────────────
@app.route("/api/tailor", methods=["POST"])
def start_tailor():
    provider = request.form.get("provider", "claude").strip()
    model    = request.form.get("model", "").strip()
    api_key  = request.form.get("api_key", "").strip() or \
               (ENV_ANTHROPIC if provider == "claude" else ENV_GEMINI)
    if not api_key:
        logger.warning("Tailor request rejected: no API key for provider=%s", provider)
        return jsonify({"error": f"No API key for {provider}."}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "step": 0, "started_at": time.time()}
    logger.info("Job=%s started (provider=%s model=%s)", job_id, provider, model or "default")

    job_url = request.form.get("job_url","").strip()
    job_text = request.form.get("job_text","").strip()
    resume_text = request.form.get("resume_text","").strip()
    job_fb, job_fn = (b := request.files.get("job_file")) and (b.read(), b.filename) or (None,"")
    res_fb, res_fn = (b := request.files.get("resume_file")) and (b.read(), b.filename) or (None,"")
    # Optional chat linkage (chat tailor flow): persisted as a RunLog on success.
    try:
        link_profile = int(request.form.get("profile_id")) if request.form.get("profile_id") else None
        link_jd = int(request.form.get("jd_id")) if request.form.get("jd_id") else None
    except (TypeError, ValueError):
        link_profile, link_jd = None, None

    threading.Thread(target=_run, args=(
        job_id, provider, model, api_key,
        job_url, job_text, job_fb, job_fn,
        resume_text, res_fb, res_fn, link_profile, link_jd
    ), daemon=True).start()
    return jsonify({"job_id": job_id})


def _run(job_id, provider, model, api_key,
         job_url, job_text, job_fb, job_fn,
         resume_text, res_fb, res_fn, link_profile=None, link_jd=None):
    log = get_logger(f"app.job.{job_id[:8]}")
    def step(n): jobs[job_id]["step"] = n
    try:
        step(0)
        if job_fb:
            log.info("Extracting JD text from uploaded file=%s", job_fn)
            jd = extract_text(job_fb, job_fn)
        elif job_url:
            import httpx
            try:
                log.info("Fetching JD from URL=%s", job_url[:120])
                r = httpx.get(job_url, timeout=15, follow_redirects=True,
                              headers={"User-Agent":"Mozilla/5.0"})
                jd = re.sub(r"\s+"," ", re.sub(r"<[^>]+>"," ", r.text)).strip()[:8000]
            except Exception as e:
                log.warning("URL fetch failed (%s); falling back to pasted JD", e)
                jd = job_text or ""
        else: jd = job_text
        resume = extract_text(res_fb, res_fn) if res_fb else resume_text
        if not jd.strip() or not resume.strip():
            jobs[job_id]={"status":"error","error":"Could not extract text."}
            log.error("Job=%s failed: empty JD or resume text", job_id)
            return
        log.info("Job=%s inputs ready (JD chars=%d, resume chars=%d)", job_id, len(jd), len(resume))

        step(1); log.debug("Fetching company context")
        web_ctx = fetch_company_context(jd, job_url or "")
        step(2); log.info("Calling LLM to tailor resume (provider=%s)", provider)
        tailored = tailor_resume(resume, jd, web_ctx, provider=provider, model=model, api_key=api_key)
        step(3); log.info("Calling LLM for cover letter")
        cover    = generate_cover_letter(resume, jd, tailored, web_ctx, provider=provider, model=model, api_key=api_key)

        step(4)
        cm = re.search(r"(?:at|@|for|join)\s+([A-Z][A-Za-z0-9&\s]{2,30}?)(?:\s*[,.]|\s+is\b|\s+we\b)", jd)
        company = cm.group(1).strip() if cm else "Company"
        lines = [l.strip() for l in jd.split("\n") if l.strip()]
        job_title = lines[0][:50] if lines else "Role"
        rp = str(OUTPUT_DIR/f"{job_id}_resume.pdf")
        cp = str(OUTPUT_DIR/f"{job_id}_cover.pdf")
        generate_resume_pdf(tailored, rp)
        generate_cover_letter_pdf(cover, cp)
        log.info("Generated PDFs: resume=%s cover=%s", rp, cp)

        step(5)
        started = jobs[job_id].get("started_at", time.time())
        jobs[job_id]={"status":"done","step":5,"resume_path":rp,"cover_path":cp,
                      "company":company,"job_title":job_title,
                      "started_at": started}
        elapsed = time.time() - started
        log.info("Job=%s completed in %.1fs (company=%s role=%s)", job_id, elapsed, company, job_title)
        # Chat linkage: persist the tailor completion as a RunLog so the
        # chat timeline (derived from run_logs) shows it after restarts.
        if link_profile is not None and link_jd is not None:
            try:
                from src.database import get_db_session
                from src.models import RunLog
                with get_db_session() as s:
                    run = RunLog(profile_id=link_profile, jd_id=link_jd,
                                 feedback={"kind": "tailor", "job_id": job_id,
                                           "company": company, "job_title": job_title},
                                 status="completed",
                                 duration_ms=int(elapsed * 1000),
                                 resume_pdf_path=rp, cover_pdf_path=cp)
                    s.add(run)
                    s.flush()
                    jobs[job_id]["run_id"] = run.id
                    log.info("Job=%s stored as run id=%d", job_id, run.id)
            except Exception as e:
                log.warning("Job=%s run persistence failed: %s", job_id, e)
    except Exception as e:
        logger.exception("Job=%s raised exception", job_id)
        jobs[job_id]={"status":"error","error":str(e)}


@app.route("/api/status/<job_id>")
def job_status(job_id):
    j = jobs.get(job_id)
    if not j:
        logger.warning("Status poll for unknown job=%s", job_id)
        abort(404)
    return jsonify({**j, "job_id": job_id})

@app.route("/api/download/<job_id>/<doc>")
def download(job_id, doc):
    j = jobs.get(job_id)
    if not j or j.get("status") != "done":
        logger.warning("Download for job=%s doc=%s rejected (status=%s)", job_id, doc, (j or {}).get("status"))
        abort(404)
    path = j["resume_path"] if doc == "resume" else j["cover_path"]
    name = f"{'Resume' if doc=='resume' else 'CoverLetter'}_{j.get('company','')}.pdf"
    logger.info("Serving %s for job=%s", path, job_id)
    return send_file(path, as_attachment=True, download_name=name, mimetype="application/pdf")

@app.route("/api/runs/<int:run_id>/download/<doc>")
def download_run(run_id, doc):
    """Restart-safe PDF download for tailor runs persisted on run_logs."""
    from pathlib import Path as _Path
    from src.database import get_db_session
    from src.models import RunLog
    if doc not in ("resume", "cover"):
        abort(404)
    with get_db_session() as s:
        run = s.query(RunLog).filter(RunLog.id == run_id).first()
        if run is None:
            abort(404)
        path = run.resume_pdf_path if doc == "resume" else run.cover_pdf_path
        if not path or not _Path(path).exists():
            abort(404)
        fb = run.feedback or {}
        name = f"{'Resume' if doc == 'resume' else 'CoverLetter'}_{fb.get('company','')}.pdf"
        logger.info("Serving run %d %s", run_id, path)
        return send_file(path, as_attachment=True, download_name=name,
                         mimetype="application/pdf")

# ── Profile & Fact API (Stage 1.4) ────────────────────────────────────────────
def _not_found(msg):
    return jsonify({"error": msg}), 404


def _unprocessable(msg):
    return jsonify({"error": msg}), 422


@app.route("/api/profile", methods=["POST"])
def api_create_profile():
    data = request.get_json(silent=True) or {}
    # Support `id` for create-or-update semantics per progress.md spec.
    pid = data.get("id")
    try:
        if pid is not None:
            result = ps.update_profile(
                int(pid), name=data.get("name"), sections=data.get("sections"),
            )
            logger.info("Updated profile id=%s via POST /api/profile", pid)
            return jsonify(result), 200
        result = ps.create_profile(
            name=data.get("name", "Default Profile"), sections=data.get("sections"),
        )
        logger.info("Created profile id=%s via POST /api/profile", result.get("id"))
        return jsonify(result), 201
    except (ProfileNotFoundError, FactNotFoundError) as e:
        return _not_found(str(e))
    except ValueError as e:
        return _unprocessable(str(e))


@app.route("/api/profiles", methods=["GET"])
def api_list_profiles():
    return jsonify(ps.list_profiles()), 200


@app.route("/api/profile/<int:pid>", methods=["GET"])
def api_get_profile(pid):
    try:
        return jsonify(ps.get_profile(pid)), 200
    except (ProfileNotFoundError, FactNotFoundError):
        abort(404)


@app.route("/api/profile/<int:pid>", methods=["DELETE"])
def api_delete_profile(pid):
    try:
        ps.delete_profile(pid)
        logger.info("Deleted profile id=%d via DELETE /api/profile", pid)
        return jsonify({"deleted": True, "id": pid}), 200
    except (ProfileNotFoundError, FactNotFoundError):
        abort(404)


@app.route("/api/profile/<int:pid>/facts", methods=["GET"])
def api_list_facts(pid):
    try:
        section = request.args.get("section")
        return jsonify(ps.list_facts(pid, section=section)), 200
    except (ProfileNotFoundError, FactNotFoundError):
        abort(404)


@app.route("/api/profile/<int:pid>/facts", methods=["POST"])
def api_add_fact(pid):
    data = request.get_json(silent=True) or {}
    if not data.get("section") or not data.get("content"):
        return jsonify({"error": "Both 'section' and 'content' are required."}), 400
    try:
        result = ps.add_fact(
            pid,
            section=data["section"],
            content=data["content"],
            is_mandatory=data.get("is_mandatory"),
        )
        return jsonify(result), 201
    except (ProfileNotFoundError, FactNotFoundError) as e:
        return _not_found(str(e))
    except ValueError as e:
        return _unprocessable(str(e))


@app.route("/api/fact/<int:fid>", methods=["PUT"])
def api_update_fact(fid):
    data = request.get_json(silent=True) or {}
    if not any(k in data for k in ("section", "content", "is_mandatory")):
        return jsonify({"error": "Nothing to update. Provide section/content/is_mandatory."}), 400
    try:
        result = ps.update_fact(
            fid,
            section=data.get("section"),
            content=data.get("content"),
            is_mandatory=data.get("is_mandatory"),
        )
        return jsonify(result), 200
    except (ProfileNotFoundError, FactNotFoundError):
        abort(404)
    except ValueError as e:
        return _unprocessable(str(e))


@app.route("/api/fact/<int:fid>", methods=["DELETE"])
def api_delete_fact(fid):
    try:
        ps.delete_fact(fid)
        return jsonify({"deleted": True, "id": fid}), 200
    except (ProfileNotFoundError, FactNotFoundError):
        abort(404)


@app.route("/api/profile/<int:pid>/ingest", methods=["POST"])
def api_ingest_profile(pid):
    try:
        ps.get_profile(pid)
    except (ProfileNotFoundError, FactNotFoundError):
        abort(404)
    upload = request.files.get("resume_file")
    try:
        if upload is not None:
            payload = upload.read()
            result = ps.ingest_document(pid, payload, filename=upload.filename or "")
        else:
            data = request.get_json(silent=True) or {}
            text = data.get("resume_text", "") or request.form.get("resume_text", "")
            if not text or not str(text).strip():
                return jsonify({"error": "Provide 'resume_file' upload or non-empty 'resume_text'."}), 400
            result = ps.ingest_resume(pid, str(text))
        logger.info("Ingested resume into profile id=%d: %s facts", pid, result.get("facts_created"))
        return jsonify(result), 201
    except (ProfileNotFoundError, FactNotFoundError) as e:
        return _not_found(str(e))
    except ValueError as e:
        return _unprocessable(str(e))

# ── Feedback Runs API (Stage 5.2) ─────────────────────────────────────────────
def _run_error(e: ValueError):
    # Missing rows -> 404; other validation -> 422.
    if "not found" in str(e).lower():
        return _not_found(str(e))
    return _unprocessable(str(e))


@app.route("/api/runs", methods=["POST"])
def api_create_run():
    from src import feedback as fb
    from src.evaluation import get_ats_checklist
    data = request.get_json(silent=True) or {}
    if data.get("profile_id") is None or data.get("jd_id") is None:
        return jsonify({"error": "Both 'profile_id' and 'jd_id' are required."}), 400
    try:
        result = fb.create_feedback_run(
            int(data["profile_id"]), int(data["jd_id"]),
            capacities=data.get("capacities"))
        checklist = get_ats_checklist(int(data["profile_id"]), int(data["jd_id"]))
        return jsonify({"run_id": result["run_id"],
                        "feedback": result["feedback"],
                        "ats_checklist": checklist,
                        "role_type": result["role_type"],
                        "total_utility": result["total_utility"]}), 201
    except (ProfileNotFoundError, FactNotFoundError) as e:
        return _not_found(str(e))
    except ValueError as e:
        return _run_error(e)


@app.route("/api/runs/<int:run_id>/rerun", methods=["POST"])
def api_rerun(run_id):
    from src import feedback as fb
    from src.evaluation import get_ats_checklist
    data = request.get_json(silent=True) or {}
    try:
        result = fb.rerun_feedback(run_id, capacities=data.get("capacities"))
        checklist = get_ats_checklist(
            result["feedback"].get("profile_id"), result["feedback"].get("jd_id"))
        return jsonify({"run_id": result["run_id"],
                        "prev_run_id": result["prev_run_id"],
                        "feedback": result["feedback"],
                        "ats_checklist": checklist,
                        "diff": result["diff"]}), 201
    except ValueError as e:
        return _run_error(e)


@app.route("/api/runs/<int:run_id>", methods=["GET"])
def api_get_run(run_id):
    from src.database import get_db_session
    from src.models import RunLog
    with get_db_session() as s:
        run = s.query(RunLog).filter(RunLog.id == run_id).first()
        if run is None:
            abort(404)
        payload = run.to_dict()
        if run.profile_id is not None and run.jd_id is not None:
            from src.evaluation import get_ats_checklist
            try:
                payload["ats_checklist"] = get_ats_checklist(
                    run.profile_id, run.jd_id, session=s)
            except ValueError:
                pass
        return jsonify(payload), 200

# ── JD & Allocation API (pre-Phase-6 UI integration) ───────────────────────────
def _public_fact(f):
    return {"id": f.get("id"), "section": f.get("section"),
            "content": f.get("content"),
            "is_mandatory": f.get("is_mandatory"),
            "utility": f.get("utility"), "best_match": f.get("best_match")}


@app.route("/api/jds", methods=["POST"])
def api_create_jd():
    from src.jd_structuring import persist_jd
    upload = request.files.get("jd_file")
    try:
        if upload is not None:
            payload = upload.read()
            text = extract_text(payload, upload.filename or "")
        else:
            data = request.get_json(silent=True) or {}
            text = data.get("raw_text", "") or request.form.get("raw_text", "")
        if not text or not str(text).strip():
            return jsonify({"error": "Provide 'jd_file' upload or non-empty 'raw_text'."}), 400
        result = persist_jd(str(text))
        logger.info("Persisted JD id=%s role=%s (%s requirements)",
                    result.get("id"), result.get("role_type"),
                    result.get("requirements_count"))
        return jsonify(result), 201
    except ValueError as e:
        return _run_error(e)


@app.route("/api/jds", methods=["GET"])
def api_list_jds():
    from src.database import get_db_session
    from src.models import JD
    with get_db_session() as s:
        rows = s.query(JD).order_by(JD.id.desc()).limit(50).all()
        return jsonify([r.to_dict() for r in rows]), 200


@app.route("/api/jds/<int:jd_id>", methods=["GET"])
def api_get_jd(jd_id):
    from src.database import get_db_session
    from src.models import JD, JDRequirement
    with get_db_session() as s:
        jd = s.query(JD).filter(JD.id == jd_id).first()
        if jd is None:
            abort(404)
        body = jd.to_dict()
        body["raw_text"] = jd.raw_text  # needed by the tailor form flow
        reqs = s.query(JDRequirement).filter(
            JDRequirement.jd_id == jd_id).order_by(JDRequirement.id).all()
        body["requirements"] = [r.to_dict() for r in reqs]
        return jsonify(body), 200


@app.route("/api/allocate", methods=["POST"])
def api_allocate():
    from src.tailor import build_allocation_context
    data = request.get_json(silent=True) or {}
    if data.get("profile_id") is None or data.get("jd_id") is None:
        return jsonify({"error": "Both 'profile_id' and 'jd_id' are required."}), 400
    try:
        ctx = build_allocation_context(
            int(data["profile_id"]), int(data["jd_id"]),
            capacities=data.get("capacities"))
        sections = {}
        for name, alloc in ctx["sections"].items():
            sections[name] = {
                "selected": [_public_fact(f) for f in alloc["selected"]],
                "dropped": [_public_fact(f) for f in alloc["dropped"]],
                "total_utility": alloc["total_utility"],
                "total_weight": alloc["total_weight"],
                "capacity": alloc["capacity"],
            }
        return jsonify({"profile_id": ctx["profile_id"], "jd_id": ctx["jd_id"],
                        "company": ctx["company"], "job_title": ctx["job_title"],
                        "role_type": ctx["role_type"],
                        "sections": sections,
                        "total_utility": ctx["total_utility"],
                        "selected_count": len(ctx["selected_facts"]),
                        "dropped_count": len(ctx["dropped_facts"])}), 200
    except (ProfileNotFoundError, FactNotFoundError) as e:
        return _not_found(str(e))
    except ValueError as e:
        return _run_error(e)

# ── Chat Threads API (1 profile : N JD chats) ─────────────────────────────────
def _thread_card(s, thread):
    from src.models import JD, RunLog
    card = thread.to_dict()
    run = None
    if thread.jd_id is not None:
        run = (s.query(RunLog)
               .filter(RunLog.profile_id == thread.profile_id,
                       RunLog.jd_id == thread.jd_id)
               .order_by(RunLog.id.desc()).first())
    card["latest_run"] = ({"id": run.id, "status": run.status,
                           "weakest_section": (run.feedback or {}).get("weakest_section"),
                           "reasoning": (run.feedback or {}).get("reasoning"),
                           "created_at": run.created_at.isoformat() if run.created_at else None}
                          if run is not None else None)
    return card


@app.route("/api/profile/<int:pid>/chats", methods=["GET"])
def api_list_chats(pid):
    from src.database import get_db_session
    from src.models import ChatThread
    try:
        ps.get_profile(pid)
    except (ProfileNotFoundError, FactNotFoundError):
        abort(404)
    with get_db_session() as s:
        threads = (s.query(ChatThread)
                   .filter(ChatThread.profile_id == pid)
                   .order_by(ChatThread.updated_at.desc()).all())
        return jsonify([_thread_card(s, t) for t in threads]), 200


@app.route("/api/profile/<int:pid>/chats", methods=["POST"])
def api_create_chat(pid):
    from src.database import get_db_session
    from src.models import ChatThread, JD
    try:
        ps.get_profile(pid)
    except (ProfileNotFoundError, FactNotFoundError):
        abort(404)
    data = request.get_json(silent=True) or {}
    try:
        with get_db_session() as s:
            jd_id = data.get("jd_id")
            if data.get("jd_text") and str(data["jd_text"]).strip():
                from src.jd_structuring import persist_jd
                # persist_jd opens its own session when session=None; pass
                # the request session explicitly is unsupported, so commit
                # ordering is: JD first (own transaction), then the thread.
                jd_id = persist_jd(str(data["jd_text"]))["id"]
            title = (data.get("title") or "").strip()
            if jd_id is not None:
                jd = s.query(JD).filter(JD.id == int(jd_id)).first()
                if jd is None:
                    return _not_found(f"JD {jd_id} not found.")
                if not title:
                    title = ((jd.job_title or "Role")
                             + (f" @ {jd.company}" if jd.company else ""))
            thread = ChatThread(profile_id=pid, jd_id=jd_id,
                                title=title or "New application")
            s.add(thread)
            s.flush()
            card = _thread_card(s, thread)
            logger.info("Created chat id=%d for profile id=%d (jd=%s)",
                        thread.id, pid, jd_id)
            return jsonify(card), 201
    except ValueError as e:
        return _run_error(e)


@app.route("/api/chats/<int:cid>", methods=["GET"])
def api_get_chat(cid):
    from src.database import get_db_session
    from src.models import ChatThread, JDRequirement, RunLog
    with get_db_session() as s:
        thread = s.query(ChatThread).filter(ChatThread.id == cid).first()
        if thread is None:
            abort(404)
        card = _thread_card(s, thread)
        if thread.jd is not None:
            reqs = (s.query(JDRequirement)
                    .filter(JDRequirement.jd_id == thread.jd_id)
                    .order_by(JDRequirement.id).all())
            card["jd"] = {**thread.jd.to_dict(),
                          "requirements": [r.to_dict() for r in reqs]}
        runs = (s.query(RunLog)
                .filter(RunLog.profile_id == thread.profile_id,
                        RunLog.jd_id == thread.jd_id)
                .order_by(RunLog.id).all()) if thread.jd_id else []
        card["runs"] = [{"id": r.id, "status": r.status,
                         "feedback": r.feedback or {},
                         "created_at": r.created_at.isoformat()
                         if r.created_at else None} for r in runs]
        return jsonify(card), 200


@app.route("/api/chats/<int:cid>", methods=["PUT"])
def api_update_chat(cid):
    from src.database import get_db_session
    from src.models import ChatThread, JD
    data = request.get_json(silent=True) or {}
    with get_db_session() as s:
        thread = s.query(ChatThread).filter(ChatThread.id == cid).first()
        if thread is None:
            abort(404)
        if "title" in data and str(data["title"]).strip():
            thread.title = str(data["title"]).strip()[:255]
        if "jd_id" in data:
            if data["jd_id"] is None:
                thread.jd_id = None
            else:
                jd = s.query(JD).filter(JD.id == int(data["jd_id"])).first()
                if jd is None:
                    return _not_found(f"JD {data['jd_id']} not found.")
                thread.jd_id = jd.id
        s.flush()
        return jsonify(_thread_card(s, thread)), 200


@app.route("/api/chats/<int:cid>", methods=["DELETE"])
def api_delete_chat(cid):
    from src.database import get_db_session
    from src.models import ChatThread
    with get_db_session() as s:
        thread = s.query(ChatThread).filter(ChatThread.id == cid).first()
        if thread is None:
            abort(404)
        s.delete(thread)
        s.flush()
        logger.info("Deleted chat id=%d", cid)
        return jsonify({"deleted": True, "id": cid}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("Starting KnapResume web server on http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
