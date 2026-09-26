"""
tests/test_chats.py
Chat threads: 1 profile : N JD chats.

Covers thread create (with jd_id, jd_text, empty), list ordering,
detail (JD + runs timeline), rename/reattach, delete cascade rules
(runs survive thread deletion), and error paths. Flask client bound
to in-memory DB. No live LLM calls.
"""

from contextlib import contextmanager

import pytest

import src.database as db_module
import src.profile_service as ps


JD_A = """\
Backend Engineer at Acme Corp

Requirements:
- 5+ years building backend systems in Python
"""

JD_B = """\
Frontend Engineer at Globex

Requirements:
- 3+ years building interfaces with React and TypeScript
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
def profile_id(in_memory_db):
    return ps.create_profile(name="Alice", session=in_memory_db)["id"]


def _jd(api_client, text):
    r = api_client.post("/api/jds", json={"raw_text": text})
    assert r.status_code == 201
    return r.get_json()["id"]


# ── CRUD ─────────────────────────────────────────────────────────────────────

def test_create_chat_with_jd_id(api_client, profile_id):
    jid = _jd(api_client, JD_A)
    r = api_client.post(f"/api/profile/{profile_id}/chats",
                        json={"jd_id": jid})
    assert r.status_code == 201
    body = r.get_json()
    assert body["profile_id"] == profile_id and body["jd_id"] == jid
    assert "Acme" in body["title"] and "Backend" in body["title"]
    assert body["latest_run"] is None


def test_create_chat_with_jd_text_persists_jd(api_client, profile_id):
    r = api_client.post(f"/api/profile/{profile_id}/chats",
                        json={"jd_text": JD_B})
    assert r.status_code == 201
    body = r.get_json()
    assert body["jd_id"] is not None
    assert body["company"] == "Globex"
    assert api_client.get(f"/api/jds/{body['jd_id']}").status_code == 200


def test_create_empty_chat_then_attach(api_client, profile_id):
    r = api_client.post(f"/api/profile/{profile_id}/chats",
                        json={"title": "Dream role"})
    assert r.status_code == 201
    cid = r.get_json()["id"]
    assert r.get_json()["jd_id"] is None

    jid = _jd(api_client, JD_A)
    r = api_client.put(f"/api/chats/{cid}", json={"jd_id": jid})
    assert r.status_code == 200
    assert r.get_json()["jd_id"] == jid


def test_list_chats_one_profile_many_jds(api_client, profile_id):
    _jd_a = _jd(api_client, JD_A)
    _jd_b = _jd(api_client, JD_B)
    api_client.post(f"/api/profile/{profile_id}/chats", json={"jd_id": _jd_a})
    api_client.post(f"/api/profile/{profile_id}/chats", json={"jd_id": _jd_b})
    listed = api_client.get(f"/api/profile/{profile_id}/chats").get_json()
    assert len(listed) == 2
    assert {c["company"] for c in listed} == {"Acme Corp", "Globex"}


def test_chat_detail_has_jd_and_runs_timeline(api_client, profile_id):
    jid = _jd(api_client, JD_A)
    cid = api_client.post(f"/api/profile/{profile_id}/chats",
                          json={"jd_id": jid}).get_json()["id"]
    run = api_client.post("/api/runs",
                          json={"profile_id": profile_id,
                                "jd_id": jid}).get_json()
    detail = api_client.get(f"/api/chats/{cid}").get_json()
    assert detail["jd"]["id"] == jid
    assert len(detail["jd"]["requirements"]) > 0
    assert [r["id"] for r in detail["runs"]] == [run["run_id"]]
    # List card now carries the latest run too.
    listed = api_client.get(f"/api/profile/{profile_id}/chats").get_json()
    assert listed[0]["latest_run"]["id"] == run["run_id"]


def test_delete_chat_keeps_runs(api_client, profile_id):
    jid = _jd(api_client, JD_A)
    cid = api_client.post(f"/api/profile/{profile_id}/chats",
                          json={"jd_id": jid}).get_json()["id"]
    run_id = api_client.post(
        "/api/runs", json={"profile_id": profile_id, "jd_id": jid}
    ).get_json()["run_id"]
    assert api_client.delete(f"/api/chats/{cid}").status_code == 200
    assert api_client.get(f"/api/chats/{cid}").status_code == 404
    assert api_client.get(f"/api/runs/{run_id}").status_code == 200


def test_delete_profile_cascades_chats(api_client, profile_id):
    jid = _jd(api_client, JD_A)
    cid = api_client.post(f"/api/profile/{profile_id}/chats",
                          json={"jd_id": jid}).get_json()["id"]
    assert api_client.delete(f"/api/profile/{profile_id}").status_code == 200
    assert api_client.get(f"/api/chats/{cid}").status_code == 404


def test_chat_errors(api_client, profile_id):
    assert api_client.get("/api/profile/99999/chats").status_code == 404
    assert api_client.post("/api/profile/99999/chats", json={}).status_code == 404
    assert api_client.post(f"/api/profile/{profile_id}/chats",
                           json={"jd_id": 99999}).status_code == 404
    assert api_client.get("/api/chats/99999").status_code == 404
    assert api_client.put("/api/chats/99999", json={"title": "x"}).status_code == 404
    assert api_client.delete("/api/chats/99999").status_code == 404
