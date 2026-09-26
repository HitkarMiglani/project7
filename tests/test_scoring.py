"""
tests/test_scoring.py
Stage 3.1 — Semantic Scoring Engine.

Covers matrix shapes, relevant-beats-irrelevant ranking, exact-mention
fuzzy bonus, importance + category weighting, determinism, precomputed
embedding reuse, and empty-input handling.
"""

import numpy as np
import pytest

from src.scoring import (
    cosine_similarity_matrix,
    fuzzy_match_matrix,
    score_facts,
)


FACTS = [
    {"id": 1, "section": "experience",
     "content": "Built ETL pipelines in Python with Postgres and Docker"},
    {"id": 2, "section": "experience",
     "content": "Baked sourdough bread and organized weekend hiking trips"},
    {"id": 3, "section": "skills", "content": "Python, Docker, Kafka"},
]

REQS = [
    {"skill": "Python", "category": "required", "importance": 1.0},
    {"skill": "Docker", "category": "required", "importance": 0.8},
    {"skill": "Spark", "category": "nice_to_have", "importance": 0.6},
]


# ── Matrices ─────────────────────────────────────────────────────────────────

def test_cosine_matrix_shape_and_range():
    mat = cosine_similarity_matrix(
        [f["content"] for f in FACTS], [r["skill"] for r in REQS])
    assert mat.shape == (3, 3)
    assert float(mat.min()) >= 0.0 and float(mat.max()) <= 1.0


def test_cosine_matrix_empty_dims():
    assert cosine_similarity_matrix([], ["Python"]).shape == (0, 1)
    assert cosine_similarity_matrix(["text"], []).shape == (1, 0)


def test_fuzzy_exact_mention_scores_one():
    mat = fuzzy_match_matrix(["Python, Docker, Kafka"], ["Python"])
    assert mat[0, 0] == pytest.approx(1.0)


# ── score_facts ranking ──────────────────────────────────────────────────────

def test_relevant_fact_beats_irrelevant():
    scored = score_facts(FACTS, REQS)
    by_id = {s["id"]: s for s in scored}
    assert by_id[1]["utility"] > by_id[2]["utility"]
    assert by_id[1]["best_match"] in {"Python", "Docker"}
    assert by_id[2]["utility"] < 0.5


def test_skill_line_gets_high_utility_via_fuzzy():
    scored = score_facts([FACTS[2]], REQS)
    assert scored[0]["utility"] > 0.5
    assert scored[0]["fuzzy"] == pytest.approx(1.0)


def test_importance_weighting():
    high = score_facts([FACTS[0]],
                       [{"skill": "Python", "category": "required",
                         "importance": 1.0}])[0]["utility"]
    low = score_facts([FACTS[0]],
                      [{"skill": "Python", "category": "required",
                        "importance": 0.2}])[0]["utility"]
    assert high > low


def test_nice_to_have_down_weighted():
    req = {"skill": "Spark", "category": "nice_to_have", "importance": 1.0}
    req_required = {"skill": "Spark", "category": "required", "importance": 1.0}
    fact = [{"section": "experience",
             "content": "Built streaming jobs with Spark on Hadoop"}]
    assert (score_facts(fact, [req_required])[0]["utility"]
            > score_facts(fact, [req])[0]["utility"])


def test_alpha_blend_endpoints():
    fact = [FACTS[0]]
    req = [REQS[0]]
    sem_only = score_facts(fact, req, alpha=1.0)[0]
    fuzz_only = score_facts(fact, req, alpha=0.0)[0]
    assert sem_only["utility"] == pytest.approx(sem_only["cosine"])
    assert fuzz_only["utility"] == pytest.approx(fuzz_only["fuzzy"])


def test_alpha_out_of_range_raises():
    with pytest.raises(ValueError):
        score_facts(FACTS, REQS, alpha=1.5)


def test_deterministic_across_calls():
    first = score_facts(FACTS, REQS)
    second = score_facts(FACTS, REQS)
    assert [s["utility"] for s in first] == [s["utility"] for s in second]


# ── Embeddings reuse + empty inputs ──────────────────────────────────────────

def test_precomputed_embeddings_match_live_encoding():
    from src.jd_structuring import _get_embed_model
    model = _get_embed_model()
    texts = [f["content"] for f in FACTS]
    skills = [r["skill"] for r in REQS]
    fact_vecs = [np.asarray(v, dtype=np.float32)
                 for v in model.encode(texts, normalize_embeddings=False)]
    req_vecs = [np.asarray(v, dtype=np.float32)
                for v in model.encode(skills, normalize_embeddings=False)]
    with_emb = score_facts(
        [{**f, "embedding": v} for f, v in zip(FACTS, fact_vecs)],
        [{**r, "embedding": v} for r, v in zip(REQS, req_vecs)],
    )
    live = score_facts(FACTS, REQS)
    for a, b in zip(with_emb, live):
        assert a["utility"] == pytest.approx(b["utility"], abs=1e-5)


def test_empty_facts_returns_empty():
    assert score_facts([], REQS) == []


def test_empty_requirements_zero_utilities():
    scored = score_facts(FACTS, [])
    assert len(scored) == 3
    assert all(s["utility"] == 0.0 and s["best_match"] is None for s in scored)
