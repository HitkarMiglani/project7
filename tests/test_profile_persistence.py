"""
tests/test_profile_persistence.py
Stage 1.4 — REST Endpoints & Persistence Testing.

Exercises the Flask profile/fact API in app.py against an isolated
in-memory SQLite session (via monkeypatched get_db_session), covering:
profile create/get/list/update/delete, fact add/list/update/delete,
section filtering, ingest (text + file upload), and 404/400/422 handling.
"""

import io
from contextlib import contextmanager

import pytest

import src.profile_service as ps


@pytest.fixture()
def client(in_memory_db, monkeypatch):
    """Flask test client with service layer bound to in-memory DB."""
    @contextmanager
    def _fake_session():
        yield in_memory_db
        in_memory_db.commit()

    monkeypatch.setattr(ps, "get_db_session", _fake_session)

    import app as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


SAMPLE_RESUME = """\
Alice Developer
alice@example.com | +1 (555) 123-4567 | github.com/alice

SUMMARY
Backend engineer with 6 years building distributed systems in Python.

EXPERIENCE
Staff Engineer | Acme Corp | 2021 - Present
- Led migration of monolith to microservices, cutting p95 latency 40%

SKILLS
Python, FastAPI, SQL, Docker
"""


# ── Profile CRUD ─────────────────────────────────────────────────────────────

def test_create_and_get_profile(client):
    r = client.post("/api/profile", json={"name": "Alice"})
    assert r.status_code == 201
    pid = r.get_json()["id"]

    r = client.get(f"/api/profile/{pid}")
    assert r.status_code == 200
    assert r.get_json()["name"] == "Alice"


def test_create_profile_empty_name_422(client):
    r = client.post("/api/profile", json={"name": "   "})
    assert r.status_code == 422


def test_update_profile_via_post_id(client):
    pid = client.post("/api/profile", json={"name": "Alice"}).get_json()["id"]
    r = client.post("/api/profile", json={"id": pid, "name": "Alice R."})
    assert r.status_code == 200
    assert r.get_json()["name"] == "Alice R."


def test_list_profiles(client):
    client.post("/api/profile", json={"name": "A"})
    client.post("/api/profile", json={"name": "B"})
    r = client.get("/api/profiles")
    assert r.status_code == 200
    assert len(r.get_json()) >= 2


def test_delete_profile_cascades(client):
    pid = client.post("/api/profile", json={"name": "Temp"}).get_json()["id"]
    client.post(f"/api/profile/{pid}/facts",
                json={"section": "experience", "content": "Did things"})
    assert client.delete(f"/api/profile/{pid}").status_code == 200
    assert client.get(f"/api/profile/{pid}").status_code == 404
    assert client.get(f"/api/profile/{pid}/facts").status_code == 404


def test_get_missing_profile_404(client):
    assert client.get("/api/profile/99999").status_code == 404


# ── Fact CRUD ────────────────────────────────────────────────────────────────

def test_add_list_filter_facts(client):
    pid = client.post("/api/profile", json={"name": "Alice"}).get_json()["id"]
    client.post(f"/api/profile/{pid}/facts",
                json={"section": "experience", "content": "Built ETL"})
    client.post(f"/api/profile/{pid}/facts",
                json={"section": "skills", "content": "Python"})

    all_facts = client.get(f"/api/profile/{pid}/facts").get_json()
    assert len(all_facts) == 2

    skills = client.get(f"/api/profile/{pid}/facts?section=skills").get_json()
    assert len(skills) == 1
    assert skills[0]["content"] == "Python"


def test_add_fact_missing_fields_400(client):
    pid = client.post("/api/profile", json={"name": "Alice"}).get_json()["id"]
    assert client.post(f"/api/profile/{pid}/facts",
                       json={"section": "experience"}).status_code == 400
    assert client.post("/api/profile/99999/facts",
                       json={"section": "s", "content": "c"}).status_code == 404


def test_update_and_delete_fact(client):
    pid = client.post("/api/profile", json={"name": "Alice"}).get_json()["id"]
    fid = client.post(f"/api/profile/{pid}/facts",
                      json={"section": "experience",
                            "content": "Built ETL"}).get_json()["id"]

    r = client.put(f"/api/fact/{fid}", json={"content": "Built ETL v2"})
    assert r.status_code == 200
    assert r.get_json()["content"] == "Built ETL v2"

    assert client.put("/api/fact/99999", json={"content": "x"}).status_code == 404
    assert client.put(f"/api/fact/{fid}", json={}).status_code == 400

    assert client.delete(f"/api/fact/{fid}").status_code == 200
    assert client.delete(f"/api/fact/{fid}").status_code == 404


# ── Ingest ───────────────────────────────────────────────────────────────────

def test_ingest_resume_text(client):
    pid = client.post("/api/profile", json={"name": "Alice"}).get_json()["id"]
    r = client.post(f"/api/profile/{pid}/ingest",
                    json={"resume_text": SAMPLE_RESUME})
    assert r.status_code == 201
    body = r.get_json()
    assert body["facts_created"] >= 5

    facts = client.get(f"/api/profile/{pid}/facts").get_json()
    assert len(facts) == body["facts_created"]


def test_ingest_file_upload(client):
    pid = client.post("/api/profile", json={"name": "Bob"}).get_json()["id"]
    r = client.post(
        f"/api/profile/{pid}/ingest",
        data={"resume_file": (io.BytesIO(SAMPLE_RESUME.encode()),
                              "resume.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201
    assert r.get_json()["facts_created"] > 0


def test_ingest_empty_400_and_missing_profile_404(client):
    pid = client.post("/api/profile", json={"name": "Alice"}).get_json()["id"]
    assert client.post(f"/api/profile/{pid}/ingest",
                       json={"resume_text": "   "}).status_code == 400
    assert client.post("/api/profile/99999/ingest",
                       json={"resume_text": SAMPLE_RESUME}).status_code == 404
