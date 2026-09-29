"""Stage 7.3 — offline end-to-end smoke: profile -> JD -> allocation ->
feedback/checklist -> claims -> verify/sanitize -> PDF -> persistence.

No live LLM calls. Verification uses cosine-only (use_nli=False) against
the shared embedding model already exercised by the suite.
"""

from src.allocator import DEFAULT_SECTION_CAPACITY
from src.claims import extract_claims
from src.feedback import build_feedback, create_feedback_run
from src.evaluation import build_ats_checklist
from src.verifier import record_claims, sanitize_text, verify_claims


JD_TEXT = """\
Backend Engineer at Acme Corp

Requirements:
- 5+ years building backend systems in Python
- Hands-on with Docker in production

Nice to have:
- Familiarity with GraphQL
"""


def test_full_path_smoke(in_memory_db, tmp_path):
    from src.jd_structuring import persist_jd
    from src.models import JDRequirement, RunLog
    from src.pdf_generator import generate_resume_pdf
    from src.profile_service import add_fact, create_profile
    from src.tailor import build_allocation_context, render_allocated_resume_text

    pid = create_profile(name="Smoke", session=in_memory_db)["id"]
    add_fact(pid, "experience", "Backend Engineer | Acme | 2020 - 2023",
             session=in_memory_db)
    add_fact(pid, "experience", "Built Python microservices with Postgres",
             session=in_memory_db)
    add_fact(pid, "experience", "Packaged services with Docker images",
             session=in_memory_db)
    jd = persist_jd(JD_TEXT, session=in_memory_db)
    jd_id = jd["id"]

    # Allocation: relevant facts selected under section budgets.
    context = build_allocation_context(pid, jd_id, session=in_memory_db)
    assert len(context["selected_facts"]) >= 2
    total_w = sum(s["total_weight"] for s in context["sections"].values())
    total_c = sum(s["capacity"] for s in context["sections"].values())
    assert total_w <= total_c + sum(
        s["mandatory_weight"] for s in context["sections"].values())

    # Feedback + ATS checklist.
    feedback = build_feedback(pid, jd_id, session=in_memory_db)
    assert feedback["weakest_section"] in (None, "experience", "skills",
                                           "projects", "education",
                                           "summary", "contact", "other")
    reqs = [{"skill": r.skill, "category": r.category}
            for r in in_memory_db.query(JDRequirement)
            .filter(JDRequirement.jd_id == jd_id).all()]
    checklist = build_ats_checklist(feedback, reqs)
    assert checklist["grade"] in ("A", "B", "C", "D")

    # Claims pipeline on allocation-rendered text (cited facts).
    rendered = render_allocated_resume_text(context["selected_facts"])
    claims = extract_claims(rendered)
    assert len(claims) > 0
    all_facts = [*context["selected_facts"], *context["dropped_facts"]]
    verified = verify_claims(claims, all_facts, use_nli=False)
    states = {v["state"] for v in verified}
    assert states <= {"verified", "inferred", "unsupported"}
    clean = sanitize_text(rendered, verified)
    assert clean["kept_count"] >= 1

    # PDF export of sanitized text.
    pdf_path = tmp_path / "smoke_resume.pdf"
    generate_resume_pdf(clean["sanitized_text"], str(pdf_path))
    assert pdf_path.exists() and pdf_path.stat().st_size > 0

    # Persistence: feedback run + claims (7.2 RunLog integration).
    run = create_feedback_run(pid, jd_id, session=in_memory_db)
    record_claims(run["run_id"], verified, session=in_memory_db)
    row = in_memory_db.query(RunLog).filter(
        RunLog.id == run["run_id"]).first()
    assert row.status == "completed"
    assert (row.feedback or {}).get("ats_checklist", {}).get("grade") in (
        "A", "B", "C", "D")
    assert len(row.claims) == len(verified)
    assert DEFAULT_SECTION_CAPACITY["experience"] == 1500
