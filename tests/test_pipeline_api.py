"""
tests/test_pipeline_api.py
Pre-Phase-6 UI integration: JD + allocation endpoints.

Covers POST /api/jds (text + file upload, validation), GET list/single,
and POST /api/allocate (selection transparency, JSON-safe, error paths).
Flask client bound to in-memory DB. No live LLM calls.
"""

import io
from contextlib import contextmanager

import pytest

import src.database as db_module
import src.profile_service as ps


JD_TEXT = """\
Backend Engineer at Acme Corp

Requirements:
- 5+ years building backend systems in Python
- Hands-on with Postgres and Docker
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
def profile_with_facts(in_memory_db):
    pid = ps.create_profile(name="Alice", session=in_memory_db)["id"]
    ps.add_fact(pid, "experience", "Backend Engineer | Acme | 2020 - 2023",
                session=in_memory_db)
    ps.add_fact(pid, "experience", "Built Python microservices with Postgres",
                session=in_memory_db)
    ps.add_fact(pid, "experience", "Organized weekend hiking trips often",
                session=in_memory_db)
    return pid


# ── /api/jds ─────────────────────────────────────────────────────────────────

def test_create_jd_from_text(api_client):
    r = api_client.post("/api/jds", json={"raw_text": JD_TEXT})
    assert r.status_code == 201
    body = r.get_json()
    assert body["company"] == "Acme Corp"
    assert body["role_type"] == "backend"
    assert "Python" in body["required_skills"]
    assert body["requirements_count"] > 0


def test_create_jd_from_file(api_client):
    r = api_client.post(
        "/api/jds",
        data={"jd_file": (io.BytesIO(JD_TEXT.encode()), "jd.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201
    assert r.get_json()["requirements_count"] > 0


def test_create_jd_validation(api_client):
    assert api_client.post("/api/jds", json={}).status_code == 400
    assert api_client.post("/api/jds", json={"raw_text": "   "}).status_code == 400


def test_list_and_get_jd(api_client):
    jid = api_client.post("/api/jds", json={"raw_text": JD_TEXT}).get_json()["id"]
    listed = api_client.get("/api/jds").get_json()
    assert any(j["id"] == jid for j in listed)
    single = api_client.get(f"/api/jds/{jid}").get_json()
    assert single["id"] == jid
    assert "Python" in single["raw_text"]
    assert len(single["requirements"]) == single["requirements_count"]
    assert api_client.get("/api/jds/99999").status_code == 404


def test_index_serves_rebranded_ui(api_client):
    r = api_client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Knapsack resume" in html
    assert "Notion" not in html
    assert "/api/runs" in html and "/api/allocate" in html
    # Attach-JD modal offers paste + file drop + existing pickers.
    assert "attach-veil" in html and "attach-jd-file" in html
    assert "attach-jd-existing" in html and "prompt(" not in html


# ── /api/allocate ────────────────────────────────────────────────────────────

def test_allocate_transparency(api_client, profile_with_facts):
    jid = api_client.post("/api/jds", json={"raw_text": JD_TEXT}).get_json()["id"]
    r = api_client.post("/api/allocate",
                        json={"profile_id": profile_with_facts, "jd_id": jid,
                              "capacities": {"experience": 90}})
    assert r.status_code == 200
    body = r.get_json()
    exp = body["sections"]["experience"]
    selected = {f["content"] for f in exp["selected"]}
    dropped = {f["content"] for f in exp["dropped"]}
    assert "Backend Engineer | Acme | 2020 - 2023" in selected
    assert "Built Python microservices with Postgres" in selected
    assert "Organized weekend hiking trips often" in dropped
    # JSON-safe: no embedding blobs leak through
    assert "embedding" not in str(exp)
    assert body["selected_count"] + body["dropped_count"] == 3


def test_allocate_validation(api_client, profile_with_facts):
    assert api_client.post("/api/allocate", json={}).status_code == 400
    jid = api_client.post("/api/jds", json={"raw_text": JD_TEXT}).get_json()["id"]
    assert api_client.post(
        "/api/allocate",
        json={"profile_id": 99999, "jd_id": jid}).status_code == 404
    assert api_client.post(
        "/api/allocate",
        json={"profile_id": profile_with_facts, "jd_id": 99999}).status_code == 404
