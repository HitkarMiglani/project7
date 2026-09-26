"""
tests/test_claims.py
Stage 4.1 — Claim Extraction & Citation Parser (fixture LLM outputs only,
no live calls).

Covers single/multiple citations, uncited bullets, malformed markers,
bullet-marker variants, continuations, header/blank handling, empty input,
prompt-side citation wiring (render IDs + allocation note), and the
mocked end-to-end allocation -> tailor -> extract path.
"""

import pytest

import src.tailor as tailor_mod
from src.claims import extract_claims
from src.tailor import (
    ALLOCATION_SOURCE_NOTE,
    render_allocated_resume_text,
)


FIXTURE_OUTPUT = """\
Alice Developer
alice@example.com

EXPERIENCE
- Led migration of monolith to microservices [F7]
- Mentored 4 engineers and drove roadmap [F8] [F9]
- Built quantum computer in garage

SKILLS
* Python and Docker [F12]
1. On-call incident response [F13]
"""


# ── extract_claims ───────────────────────────────────────────────────────────

def test_single_and_multiple_citations():
    claims = extract_claims(FIXTURE_OUTPUT)
    by_text = {c["text"]: c["cited_fact_ids"] for c in claims}
    assert by_text["Led migration of monolith to microservices"] == [7]
    assert by_text["Mentored 4 engineers and drove roadmap"] == [8, 9]
    assert by_text["Python and Docker"] == [12]


def test_uncited_bullet_yields_empty_ids():
    claims = extract_claims(FIXTURE_OUTPUT)
    uncited = [c for c in claims if not c["cited_fact_ids"]]
    assert len(uncited) == 1
    assert uncited[0]["text"] == "Built quantum computer in garage"


def test_malformed_markers_ignored():
    claims = extract_claims("- Did things [F] [Fx] [12] [F42]")
    assert claims[0]["cited_fact_ids"] == [42]
    assert claims[0]["text"] == "Did things"


def test_marker_only_bullet_dropped():
    assert extract_claims("- [F7]\n- Real claim [F8]") == [
        {"text": "Real claim", "cited_fact_ids": [8], "raw": "Real claim [F8]"}]


def test_continuation_lines_join_bullet():
    claims = extract_claims("- Led migration of monolith\n  to microservices [F7]")
    assert len(claims) == 1
    assert claims[0]["text"] == "Led migration of monolith to microservices"
    assert claims[0]["cited_fact_ids"] == [7]


def test_headers_and_prose_ignored():
    claims = extract_claims("Alice Developer\nalice@x.io\n\nEXPERIENCE\n- Did X [F1]")
    assert len(claims) == 1
    assert claims[0]["text"] == "Did X"


def test_empty_input_returns_empty():
    assert extract_claims("") == []
    assert extract_claims("   \n  ") == []


def test_non_string_raises():
    with pytest.raises(ValueError):
        extract_claims(None)


# ── Prompt-side wiring ───────────────────────────────────────────────────────

def test_render_includes_fact_ids():
    text = render_allocated_resume_text([
        {"id": 7, "section": "experience", "content": "Did X"},
        {"section": "skills", "content": "Python"},
    ])
    assert "[F7] Did X" in text
    assert "Python" in text


def test_render_without_ids_backward_compatible():
    text = render_allocated_resume_text(
        [{"id": 7, "section": "experience", "content": "Did X"}],
        with_ids=False)
    assert "[F7]" not in text and "Did X" in text


def test_allocation_note_demands_citations():
    assert "[F" in ALLOCATION_SOURCE_NOTE
    assert "fabrication" in ALLOCATION_SOURCE_NOTE.lower()


def test_end_to_end_prompt_claims_roundtrip(monkeypatch):
    captured = {}

    def _fake_call_ai(system, user, provider, model, api_key, max_tokens=4096):
        captured["user"] = user
        return "- Rewrote services for scale [F3]\n- Invented teleportation"

    monkeypatch.setattr(tailor_mod, "_call_ai", _fake_call_ai)
    out = tailor_mod.tailor_resume(
        render_allocated_resume_text(
            [{"id": 3, "section": "experience", "content": "Rewrote services"}]),
        "Backend role", provider="claude", model="m", api_key="k",
        source_note=ALLOCATION_SOURCE_NOTE,
    )
    assert "[F3]" in captured["user"]  # IDs reach the prompt
    claims = extract_claims(out)
    assert claims[0]["cited_fact_ids"] == [3]
    assert claims[1]["cited_fact_ids"] == []  # fabrication is detectable
