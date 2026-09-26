"""
tests/test_tailor_runs.py
Tailor completions posted into chats: _run() persists a tailor RunLog when
linked (profile_id + jd_id), and /api/runs/<id>/download/<doc> serves the
PDFs restart-safely. LLM + web calls mocked; PDF generation is real.
"""

import time
from contextlib import contextmanager
from pathlib import Path

import pytest

import src.database as db_module
import src.profile_service as ps


JD_TEXT = """\
Backend Engineer at Acme Corp

Requirements:
- 5+ years building backend systems in Python
"""


@pytest.fixture()
def api_client(in_memory_db, monkeypatch):
    @contextmanager
    def _fake_session():
        yield in_memory_db
        in_memory_db.commit()

    monkeypatch.setattr(db_module, "get_db_session", _fake_session)
    monkeypatch.setattr(ps, "get_db_session", _fake_session)

    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture()
def linked_ids(api_client, in_memory_db):
    pid = api_client.post("/api/profile", json={"name": "Alice"}).get_json()["id"]
    jid = api_client.post("/api/jds", json={"raw_text": JD_TEXT}).get_json()["id"]
    return pid, jid


def _run_linked(app_module, pid, jid, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "fetch_company_context", lambda jd, url: "")
    monkeypatch.setattr(app_module, "tailor_resume",
                        lambda *a, **k: "TAILORED RESUME TEXT")
    monkeypatch.setattr(app_module, "generate_cover_letter",
                        lambda *a, **k: "COVER LETTER TEXT")
    monkeypatch.setattr(app_module, "OUTPUT_DIR", Path(tmp_path))
    job_id = "test-job-123"
    app_module.jobs[job_id] = {"status": "running", "step": 0,
                               "started_at": time.time()}
    app_module._run(job_id, "claude", "m", "k", "", JD_TEXT, None, "",
                    "Alice resume text", None, "", pid, jid)
    return job_id


def test_run_persists_tailor_runlog(api_client, in_memory_db, linked_ids,
                                    monkeypatch, tmp_path):
    import app as app_module
    pid, jid = linked_ids
    job_id = _run_linked(app_module, pid, jid, monkeypatch, tmp_path)

    job = app_module.jobs[job_id]
    assert job["status"] == "done"
    assert "run_id" in job

    from src.models import RunLog
    run = in_memory_db.query(RunLog).filter(RunLog.id == job["run_id"]).one()
    assert run.status == "completed"
    assert run.feedback["kind"] == "tailor"
    assert Path(run.resume_pdf_path).exists()
    assert Path(run.cover_pdf_path).exists()

    # The tailor run shows up in the chat timeline.
    cid = api_client.post(f"/api/profile/{pid}/chats",
                          json={"jd_id": jid}).get_json()["id"]
    detail = api_client.get(f"/api/chats/{cid}").get_json()
    kinds = [r["feedback"].get("kind") for r in detail["runs"]]
    assert "tailor" in kinds


def test_unlinked_run_stays_ephemeral(api_client, monkeypatch, tmp_path):
    import app as app_module
    monkeypatch.setattr(app_module, "fetch_company_context", lambda jd, url: "")
    monkeypatch.setattr(app_module, "tailor_resume", lambda *a, **k: "T")
    monkeypatch.setattr(app_module, "generate_cover_letter", lambda *a, **k: "C")
    monkeypatch.setattr(app_module, "OUTPUT_DIR", Path(tmp_path))
    job_id = "test-job-456"
    app_module.jobs[job_id] = {"status": "running", "step": 0,
                               "started_at": time.time()}
    app_module._run(job_id, "claude", "m", "k", "", JD_TEXT, None, "",
                    "resume", None, "")
    assert app_module.jobs[job_id]["status"] == "done"
    assert "run_id" not in app_module.jobs[job_id]


def test_run_download_serves_persisted_pdfs(api_client, in_memory_db, linked_ids,
                                            monkeypatch, tmp_path):
    import app as app_module
    pid, jid = linked_ids
    job_id = _run_linked(app_module, pid, jid, monkeypatch, tmp_path)
    run_id = app_module.jobs[job_id]["run_id"]

    for doc in ("resume", "cover"):
        r = api_client.get(f"/api/runs/{run_id}/download/{doc}")
        assert r.status_code == 200
        assert r.content_type == "application/pdf"
        assert r.data[:4] == b"%PDF"

    assert api_client.get(f"/api/runs/{run_id}/download/summary").status_code == 404
    assert api_client.get("/api/runs/99999/download/resume").status_code == 404


def test_run_download_missing_file_404(api_client, in_memory_db):
    from src.models import RunLog
    in_memory_db.add(RunLog(profile_id=None, jd_id=None, status="completed",
                            feedback={"kind": "tailor"},
                            resume_pdf_path="/nonexistent/x.pdf"))
    in_memory_db.commit()
    run_id = in_memory_db.query(RunLog).order_by(RunLog.id.desc()).first().id
    assert api_client.get(f"/api/runs/{run_id}/download/resume").status_code == 404
