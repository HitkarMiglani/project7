"""
tests/test_verifier.py
Stages 4.2 (hybrid verification) + 4.3 (sanitization & persistence).

Fast deterministic unit tests stub the model seams (cosine_to_facts /
nli_judge); a small set of live-model tests pins real behavior
(identical -> Verified, unrelated -> Unsupported). No live LLM calls.
"""

import pytest

import src.verifier as verifier_mod
from src.verifier import (
    cosine_to_facts,
    record_claims,
    sanitize_text,
    verify_claim,
    verify_claims,
)


FACTS = [
    {"id": 1, "content": "Built Python microservices with Postgres"},
    {"id": 2, "content": "Led a team of 5 engineers"},
]


def _claim(text, ids=None):
    return {"text": text, "cited_fact_ids": ids or [], "raw": text}


# ── Live cosine behavior ─────────────────────────────────────────────────────

def test_identical_claim_verified_fast_path():
    score, best = cosine_to_facts(FACTS[0]["content"], FACTS)
    assert score == pytest.approx(1.0)
    assert best["id"] == 1
    result = verify_claim(_claim(FACTS[0]["content"], [1]), FACTS)
    assert result["state"] == "verified" and result["method"] == "cosine"


def test_unrelated_claim_unsupported_fast_path():
    result = verify_claim(
        _claim("Won Olympic gold medal in swimming", [1]), FACTS)
    assert result["state"] == "unsupported" and result["method"] == "cosine"


def test_uncited_verbatim_still_verifies_against_all_facts():
    result = verify_claim(_claim(FACTS[1]["content"]), FACTS)
    assert result["state"] == "verified"
    assert result["cited_fact_id"] == 2


def test_live_paraphrase_verifies():
    result = verify_claim(
        _claim("Developed microservices in Python using Postgres", [1]), FACTS)
    assert result["state"] == "verified"


# ── NLI mapping (stubbed cosine forces the borderline band) ────────────────

def _borderline(monkeypatch, score=0.75):
    monkeypatch.setattr(
        verifier_mod, "cosine_to_facts",
        lambda text, facts: (score, facts[0]))


def test_nli_entailment_neutral_contradiction(monkeypatch):
    _borderline(monkeypatch)
    cases = [("entailment", "verified"), ("neutral", "inferred"),
             ("contradiction", "unsupported")]
    for label, expected in cases:
        monkeypatch.setattr(
            verifier_mod, "nli_judge",
            lambda c, f, _label=label: {
                "label": _label,
                "probabilities": {_label: 0.9, "other": 0.05, "x": 0.05}})
        result = verify_claim(_claim("Some borderline claim", [1]), FACTS)
        assert result["state"] == expected, label
        assert result["method"] == f"nli-{label}"


def test_nli_failure_falls_back_to_cosine_midpoint(monkeypatch):
    def _boom():
        raise RuntimeError("no model")

    monkeypatch.setattr(verifier_mod, "_get_nli_model", _boom)
    _borderline(monkeypatch, score=0.75)
    assert verify_claim(_claim("c", [1]), FACTS)["state"] == "inferred"
    _borderline(monkeypatch, score=0.65)
    result = verify_claim(_claim("c", [1]), FACTS)
    assert result["state"] == "unsupported"
    assert result["method"] == "cosine-fallback"


def test_use_nli_false_skips_model(monkeypatch):
    _borderline(monkeypatch)
    called = []
    monkeypatch.setattr(verifier_mod, "nli_judge",
                        lambda c, f: called.append(True) or {"label": "entailment",
                                                             "probabilities": {}})
    result = verify_claim(_claim("c", [1]), FACTS, use_nli=False)
    assert called == [] and result["method"] == "cosine-fallback"


# ── Degenerate inputs ────────────────────────────────────────────────────────

def test_empty_text_and_no_facts_unsupported():
    assert verify_claim(_claim("", [1]), FACTS)["state"] == "unsupported"
    result = verify_claim(_claim("Something", [1]), [])
    assert result["state"] == "unsupported"
    assert result["method"] == "no-evidence"


def test_unknown_citation_falls_back_to_all_facts():
    result = verify_claim(_claim(FACTS[0]["content"], [999]), FACTS)
    assert result["state"] == "verified"


def test_verify_claims_counts_and_order():
    claims = [_claim(FACTS[0]["content"], [1]),
              _claim("Won Olympic gold in swimming", [1])]
    results = verify_claims(claims, FACTS, use_nli=False)
    assert [r["state"] for r in results] == ["verified", "unsupported"]
    assert verify_claims([], FACTS) == []


# ── Stage 4.3: sanitize_text ────────────────────────────────────────────────

GENERATED = """\
Alice Developer

EXPERIENCE
- Built Python microservices with Postgres
- Won Olympic gold medal in swimming
  while on sabbatical
- Led a team of 5 engineers

SKILLS
- Python, Postgres
"""


def test_sanitize_drops_unsupported_keeps_rest():
    verified = verify_claims(
        [{"text": "Built Python microservices with Postgres",
          "cited_fact_ids": [1], "raw": "Built Python microservices with Postgres"},
         {"text": "Won Olympic gold medal in swimming while on sabbatical",
          "cited_fact_ids": [1],
          "raw": "Won Olympic gold medal in swimming while on sabbatical"},
         {"text": "Led a team of 5 engineers",
          "cited_fact_ids": [2], "raw": "Led a team of 5 engineers"}],
        FACTS, use_nli=False)
    assert [v["state"] for v in verified] == ["verified", "unsupported", "verified"]
    result = sanitize_text(GENERATED, verified)
    assert "Won Olympic gold" not in result["sanitized_text"]
    assert "while on sabbatical" not in result["sanitized_text"]  # continuation
    assert "Built Python microservices with Postgres" in result["sanitized_text"]
    assert "Led a team of 5 engineers" in result["sanitized_text"]
    assert "EXPERIENCE" in result["sanitized_text"]  # headers preserved
    assert result["blocked"] == [
        "Won Olympic gold medal in swimming while on sabbatical"]
    assert result["kept_count"] == 2


def test_sanitize_no_blocked_returns_text_unchanged():
    verified = [{"text": "a", "state": "verified", "raw": "a"}]
    result = sanitize_text("Header\n- a", verified)
    assert result["sanitized_text"] == "Header\n- a"
    assert result["blocked"] == []


# ── Stage 4.3: record_claims ────────────────────────────────────────────────

def test_record_claims_persists_rows(in_memory_db):
    from src.models import Claim, RunLog
    run = RunLog(profile_id=None, jd_id=None, status="completed")
    in_memory_db.add(run)
    in_memory_db.commit()
    verified = [{"text": "Built Python microservices",
                 "state": "verified", "score": 0.95, "cited_fact_id": None},
                {"text": "Won Olympic gold",
                 "state": "unsupported", "score": 0.1, "cited_fact_id": None}]
    out = record_claims(run.id, verified, session=in_memory_db)
    assert len(out) == 2
    rows = in_memory_db.query(Claim).filter(
        Claim.run_log_id == run.id).order_by(Claim.id).all()
    assert [r.state for r in rows] == ["verified", "unsupported"]
    assert rows[0].score == pytest.approx(0.95)


def test_record_claims_missing_run_raises(in_memory_db):
    with pytest.raises(ValueError, match="[Rr]un[Ll]og.*not found"):
        record_claims(99999, [], session=in_memory_db)


# ── Stage 4.4: adversarial suite ─────────────────────────────────────────────
# Every fabrication class must be Unsupported (detected) AND removed by
# sanitize_text (blocked): 100% detection + blocking rate.

ADVERSARIALS = [
    # (claim text, cited ids, fabrication class)
    ("Increased company revenue by 300% in one quarter", [1],
     "fabricated-metric"),
    ("Cut infrastructure costs by $5M annually", [],
     "fabricated-metric-uncited"),
    ("Chief Technology Officer leading 200 engineers", [1],
     "unearned-title"),
    ("Promoted to Senior Director after six months", [2],
     "unearned-title"),
    ("Certified expert in quantum cryptography and Rust", [1],
     "absent-skill"),
    ("10 years of Haskell and COBOL development", [2],
     "absent-skill"),
]

LEGIT = [
    ("Built Python microservices with Postgres", [1]),
    ("Led a team of 5 engineers", [2]),
]


def test_adversarials_all_unsupported_live():
    for text, ids, kind in ADVERSARIALS:
        result = verify_claim({"text": text, "cited_fact_ids": ids,
                               "raw": text}, FACTS)
        assert result["state"] == "unsupported", f"{kind}: {text}"


def test_adversarial_blocking_rate_100_percent():
    from src.claims import extract_claims

    def _line(text, ids):
        suffix = " " + " ".join(f"[F{i}]" for i in ids) if ids else ""
        return f"- {text}{suffix}"

    generated = "EXPERIENCE\n" + "\n".join(
        _line(t, i) for t, i in LEGIT + [(t, i) for t, i, _ in ADVERSARIALS])
    claims = extract_claims(generated)
    results = verify_claims(claims, FACTS)
    by_text = {r["text"]: r["state"] for r in results}
    for text, _, kind in ADVERSARIALS:
        assert by_text.get(text) == "unsupported", f"missed {kind}: {text}"
    for text, _ in LEGIT:
        assert by_text.get(text) == "verified", f"false positive: {text}"
    sanitized = sanitize_text(generated, results)
    assert len(sanitized["blocked"]) == len(ADVERSARIALS)
    for text, _, _ in ADVERSARIALS:
        assert text not in sanitized["sanitized_text"]
    for text, _ in LEGIT:
        assert text in sanitized["sanitized_text"]


def test_adversarial_citation_does_not_rescue_fabrication():
    # Exaggerated metric grafted onto a real fact: citation overlap must
    # never earn Verified (Unsupported blocked; Inferred flagged for review).
    result = verify_claim(
        {"text": "Built Python microservices serving 10 billion users",
         "cited_fact_ids": [1], "raw": "x"}, FACTS)
    assert result["state"] in {"unsupported", "inferred"}
    assert result["state"] != "verified"
