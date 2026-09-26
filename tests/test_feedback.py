"""
tests/test_feedback.py
Phase 5 — Weakest-Section Feedback Loop (Stages 5.1–5.3).

Covers gap analysis units (no models), the build/rerun service loop
(edit-fact → improved metrics), RunLog persistence, and the /api/runs
endpoints (Flask client bound to in-memory DB). No live LLM calls.
"""

from contextlib import contextmanager

import pytest

import src.database as db_module
import src.profile_service as ps
from src.feedback import (
    analyze_gaps,
    build_feedback,
    create_feedback_run,
    diff_feedback,
    rerun_feedback,
)


K8S_JD = """\
Backend Engineer at Acme Corp

Requirements:
- 5+ years building backend systems in Python
- Hands-on with Kubernetes in production
"""


def _scored(section, skill, utility):
    return {"section": section, "content": f"{skill} work",
            "utility": utility, "best_match": skill}


# ── Stage 5.1: analyze_gaps units ────────────────────────────────────────────

def test_weakest_section_and_reasoning():
    scored = [_scored("experience", "Python", 0.9),
              _scored("experience", "Docker", 0.2),
              _scored("skills", "Python", 0.8)]
    reqs = [{"skill": "Python", "category": "required", "importance": 1.0},
            {"skill": "Docker", "category": "required", "importance": 1.0},
            {"skill": "Spark", "category": "nice_to_have", "importance": 0.5}]
    gaps = analyze_gaps(scored, reqs)
    assert gaps["weakest_section"] == "skills"
    exp = gaps["sections"]["experience"]
    assert exp["matched"] == 1 and exp["missing"] == ["Docker"]
    assert exp["reasoning"] == (
        "Matched 1/2 required skills in Experience; missing: Docker")
    # nice_to_have skills never count as gaps
    assert "Spark" not in exp["missing"]


def test_fully_covered_has_no_weakest():
    scored = [_scored("experience", "Python", 0.9),
              _scored("experience", "Docker", 0.8)]
    reqs = [{"skill": "Python", "category": "required", "importance": 1.0},
            {"skill": "Docker", "category": "required", "importance": 1.0}]
    gaps = analyze_gaps(scored, reqs)
    assert gaps["weakest_section"] is None
    assert gaps["reasoning"] == "No gaps found"


def test_empty_inputs():
    gaps = analyze_gaps([], [])
    assert gaps["weakest_section"] is None
    assert gaps["sections"] == {}


def test_tie_break_lowest_utility():
    scored = [_scored("experience", "Python", 0.9),
              _scored("projects", "Python", 0.6)]
    reqs = [{"skill": "Python", "category": "required", "importance": 1.0},
            {"skill": "Go", "category": "required", "importance": 1.0}]
    gaps = analyze_gaps(scored, reqs)
    assert gaps["weakest_section"] == "projects"  # same coverage, less utility


# ── Service loop (in-memory DB) ──────────────────────────────────────────────

@pytest.fixture()
def k8s_setup(in_memory_db):
    from src.jd_structuring import persist_jd
    from src.profile_service import add_fact, create_profile
    pid = create_profile(name="Alice", session=in_memory_db)["id"]
    add_fact(pid, "experience", "Backend Engineer | Acme | 2020 - 2023",
             session=in_memory_db)
    add_fact(pid, "experience", "Built Python microservices with Postgres",
             session=in_memory_db)
    jd = persist_jd(K8S_JD, session=in_memory_db)
    return {"profile_id": pid, "jd_id": jd["id"]}


def test_build_feedback_names_missing_skill(in_memory_db, k8s_setup):
    feedback = build_feedback(k8s_setup["profile_id"], k8s_setup["jd_id"],
                              session=in_memory_db)
    assert feedback["weakest_section"] == "experience"
    assert "Kubernetes" in feedback["reasoning"]
    assert feedback["selected_count"] > 0


def test_edit_fact_then_rerun_improves_metrics(in_memory_db, k8s_setup):
    from src.profile_service import add_fact
    first = create_feedback_run(k8s_setup["profile_id"], k8s_setup["jd_id"],
                                session=in_memory_db)
    assert first["feedback"]["sections"]["experience"]["missing"] == ["Kubernetes"]

    add_fact(k8s_setup["profile_id"], "experience",
             "Deployed services on Kubernetes clusters",
             session=in_memory_db)
    second = rerun_feedback(first["run_id"], session=in_memory_db)
    assert second["prev_run_id"] == first["run_id"]
    assert second["run_id"] != first["run_id"]
    exp_diff = second["diff"]["experience"]
    assert exp_diff["newly_matched"] == ["Kubernetes"]
    assert exp_diff["delta"] > 0
    assert second["feedback"]["sections"]["experience"]["missing"] == []


def test_rerun_missing_run_raises(in_memory_db):
    with pytest.raises(ValueError, match="[Rr]un[Ll]og.*not found"):
        rerun_feedback(99999, session=in_memory_db)


def test_diff_feedback_standalone():
    prev = {"feedback": {"sections": {
        "experience": {"coverage": 0.5, "missing": ["Kubernetes"]}}}}
    cur = {"feedback": {"sections": {
        "experience": {"coverage": 1.0, "missing": []}}}}
    diff = diff_feedback(prev, cur)
    assert diff["experience"]["delta"] == pytest.approx(0.5)
    assert diff["experience"]["newly_matched"] == ["Kubernetes"]


# ── Stage 5.2: API endpoints ─────────────────────────────────────────────────

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


def test_runs_crud_and_rerun_flow(api_client, k8s_setup):
    pid, jd_id = k8s_setup["profile_id"], k8s_setup["jd_id"]
    r = api_client.post("/api/runs",
                        json={"profile_id": pid, "jd_id": jd_id})
    assert r.status_code == 201
    run_id = r.get_json()["run_id"]
    assert "Kubernetes" in r.get_json()["feedback"]["reasoning"]

    r = api_client.get(f"/api/runs/{run_id}")
    assert r.status_code == 200
    assert r.get_json()["status"] == "completed"

    api_client.post(f"/api/profile/{pid}/facts",
                    json={"section": "experience",
                          "content": "Deployed services on Kubernetes clusters"})
    r = api_client.post(f"/api/runs/{run_id}/rerun")
    assert r.status_code == 201
    body = r.get_json()
    assert body["diff"]["experience"]["newly_matched"] == ["Kubernetes"]


def test_runs_validation_errors(api_client, k8s_setup):
    assert api_client.post("/api/runs", json={}).status_code == 400
    assert api_client.post(
        "/api/runs", json={"profile_id": 99999,
                           "jd_id": k8s_setup["jd_id"]}).status_code == 404
    assert api_client.post(
        "/api/runs",
        json={"profile_id": k8s_setup["profile_id"], "jd_id": 99999}
    ).status_code == 404
    assert api_client.post("/api/runs/99999/rerun").status_code == 404
    assert api_client.get("/api/runs/99999").status_code == 404
