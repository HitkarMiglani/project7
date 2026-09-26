"""
tests/test_orchestration.py
Stages 3.3 (pipeline integration) + 3.4 (end-to-end allocation edges).

Verifies build_allocation_context() over a real profile + persisted JD,
the LLM prompt constraint (mocked _call_ai: dropped facts absent, selected
present, allocation note present), and orchestration error paths. No live
LLM calls.
"""

import pytest

import src.tailor as tailor_mod
from src.profile_service import (
    ProfileNotFoundError,
    add_fact,
    create_profile,
)
from src.jd_structuring import persist_jd
from src.tailor import (
    ALLOCATION_SOURCE_NOTE,
    build_allocation_context,
    render_allocated_resume_text,
    tailor_resume_with_allocation,
)


BACKEND_JD = """\
Backend Engineer at Acme Corp

Requirements:
- 5+ years building backend systems in Python
- Hands-on with Postgres and Docker

Nice to Have:
- Familiarity with Kafka
"""


@pytest.fixture()
def backend_setup(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    pid = profile["id"]
    add_fact(pid, "experience", "Backend Engineer | Acme | 2020 - 2023",
             session=in_memory_db)  # mandatory heading
    add_fact(pid, "experience", "Built Python microservices with Postgres",
             session=in_memory_db)
    add_fact(pid, "experience", "Organized weekend hiking trips often",
             session=in_memory_db)
    jd = persist_jd(BACKEND_JD, session=in_memory_db)
    return {"profile_id": pid, "jd_id": jd["id"]}


# ── build_allocation_context ─────────────────────────────────────────────────

def test_context_selects_relevant_drops_filler(in_memory_db, backend_setup):
    ctx = build_allocation_context(
        backend_setup["profile_id"], backend_setup["jd_id"],
        session=in_memory_db, capacities={"experience": 90},
    )
    exp = ctx["sections"]["experience"]
    selected = {f["content"] for f in exp["selected"]}
    dropped = {f["content"] for f in exp["dropped"]}
    assert "Backend Engineer | Acme | 2020 - 2023" in selected  # mandatory
    assert "Built Python microservices with Postgres" in selected
    assert "Organized weekend hiking trips often" in dropped
    assert ctx["total_utility"] > 0
    assert ctx["role_type"] == "backend"


def test_context_missing_profile_raises(in_memory_db, backend_setup):
    with pytest.raises(ProfileNotFoundError):
        build_allocation_context(99999, backend_setup["jd_id"],
                                 session=in_memory_db)


def test_context_missing_jd_raises(in_memory_db, backend_setup):
    with pytest.raises(ValueError, match="[Jj][Dd].*not found"):
        build_allocation_context(backend_setup["profile_id"], 99999,
                                 session=in_memory_db)


# ── Prompt constraint (mocked LLM) ───────────────────────────────────────────

def test_tailor_prompt_constrained_to_subset(in_memory_db, backend_setup,
                                            monkeypatch):
    captured = {}

    def _fake_call_ai(system, user, provider, model, api_key, max_tokens=4096):
        captured["user"] = user
        return "TAILORED OUTPUT"

    monkeypatch.setattr(tailor_mod, "_call_ai", _fake_call_ai)
    result = tailor_resume_with_allocation(
        backend_setup["profile_id"], backend_setup["jd_id"],
        provider="claude", model="test-model", api_key="test-key",
        session=in_memory_db, capacities={"experience": 90},
    )
    assert result["tailored_text"] == "TAILORED OUTPUT"
    user = captured["user"]
    assert "Built Python microservices with Postgres" in user
    assert "Organized weekend hiking trips often" not in user
    assert ALLOCATION_SOURCE_NOTE.split(" — ")[0][:40] in user


def test_tailor_empty_profile_raises(in_memory_db, monkeypatch):
    from src.profile_service import create_profile as _cp
    pid = _cp(name="Empty", session=in_memory_db)["id"]
    jd = persist_jd(BACKEND_JD, session=in_memory_db)
    with pytest.raises(ValueError, match="[Nn]o facts selected"):
        tailor_resume_with_allocation(pid, jd["id"], api_key="k",
                                      session=in_memory_db)


# ── render helper ────────────────────────────────────────────────────────────

def test_render_groups_by_section():
    facts = [
        {"section": "experience", "content": "Did X"},
        {"section": "skills", "content": "Python"},
        {"section": "experience", "content": "Did Y"},
    ]
    text = render_allocated_resume_text(facts)
    assert "EXPERIENCE" in text and "SKILLS" in text
    assert text.index("Did X") < text.index("Did Y")
    assert render_allocated_resume_text([]) == ""
