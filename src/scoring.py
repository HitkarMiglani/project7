"""
src/scoring.py
Stage 3.1 — Semantic Scoring Engine.

Computes net fact utility v_i for knapsack allocation (Stage 3.2):

    v_i = max_j( (alpha * cos(f_i, r_j) + (1 - alpha) * fuzz(f_i, r_j))
                 * importance_j * category_weight_j )

  - cos: cosine similarity of all-MiniLM-L6-v2 embeddings (shared singleton
    from src.jd_structuring, clipped at 0 — negative similarity carries no
    selection signal).
  - fuzz: rapidfuzz token_set_ratio / 100 (exact skill mentions score ~1.0
    even when phrased tersely, e.g. "Python, Docker" skill lines).
  - importance: per-requirement weight from extract_requirements (0..1).
  - category_weight: required=1.0, nice_to_have=0.5 by default.

Inputs are plain dicts (matching ProfileFact.to_dict / JDRequirement.to_dict
shapes); precomputed float32 embeddings may be passed through under the
"embedding" key to skip re-encoding. Pure + deterministic: no randomness,
no DB access. Empty fact list -> []; empty requirements -> zero utilities.
"""

from typing import Any, Dict, List, Optional

import numpy as np
from rapidfuzz import fuzz as _rf_fuzz

from src.logger import get_logger

logger = get_logger("scoring")

DEFAULT_ALPHA = 0.7
DEFAULT_CATEGORY_WEIGHTS = {"required": 1.0, "nice_to_have": 0.5}


def _as_array(vec: Any) -> Optional[np.ndarray]:
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float32).ravel()
    return arr if arr.size else None


def _encode(texts: List[str]) -> np.ndarray:
    from src.jd_structuring import _get_embed_model
    model = _get_embed_model()
    return np.asarray(
        model.encode(texts, normalize_embeddings=True), dtype=np.float32)


def cosine_similarity_matrix(
    fact_texts: List[str],
    req_skills: List[str],
    fact_embeddings: Optional[List[Any]] = None,
    req_embeddings: Optional[List[Any]] = None,
) -> np.ndarray:
    """
    Cosine similarity matrix (n_facts x n_reqs), clipped to [0, 1].
    Precomputed embeddings (when supplied for every row) skip encoding.
    """
    n, m = len(fact_texts), len(req_skills)
    if n == 0 or m == 0:
        return np.zeros((n, m), dtype=np.float32)
    fact_vecs = None
    req_vecs = None
    if fact_embeddings is not None and all(v is not None for v in fact_embeddings):
        fact_vecs = np.stack([_as_array(v) for v in fact_embeddings]).astype(np.float32)
    if req_embeddings is not None and all(v is not None for v in req_embeddings):
        req_vecs = np.stack([_as_array(v) for v in req_embeddings]).astype(np.float32)
    if fact_vecs is None:
        fact_vecs = _encode([t if t else " " for t in fact_texts])
    if req_vecs is None:
        req_vecs = _encode([s if s else " " for s in req_skills])
    # L2-normalize defensively (precomputed vectors may not be normalized).
    fact_vecs = fact_vecs / np.maximum(
        np.linalg.norm(fact_vecs, axis=1, keepdims=True), 1e-9)
    req_vecs = req_vecs / np.maximum(
        np.linalg.norm(req_vecs, axis=1, keepdims=True), 1e-9)
    sims = fact_vecs @ req_vecs.T
    return np.clip(sims, 0.0, 1.0).astype(np.float32)


def fuzzy_match_matrix(
    fact_texts: List[str], req_skills: List[str]
) -> np.ndarray:
    """
    Fuzzy match matrix (n_facts x n_reqs) in [0, 1].

    max(token_set_ratio, partial_ratio) / 100: token_set handles
    reordered/paraphrased overlap while partial_ratio gives full marks to
    exact skill mentions inside longer lines ("Python, Docker, Kafka").
    """
    n, m = len(fact_texts), len(req_skills)
    mat = np.zeros((n, m), dtype=np.float32)
    for i, fact in enumerate(fact_texts):
        for j, skill in enumerate(req_skills):
            mat[i, j] = max(
                _rf_fuzz.token_set_ratio(fact or "", skill or ""),
                _rf_fuzz.partial_ratio(fact or "", skill or ""),
            ) / 100.0
    return mat


def score_facts(
    facts: List[Dict[str, Any]],
    requirements: List[Dict[str, Any]],
    alpha: float = DEFAULT_ALPHA,
    category_weights: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Score each fact against all requirements. Returns one dict per fact
    (input order): {index, id, section, content, utility, cosine, fuzzy,
    best_match}. utility/cosine/fuzzy in [0, 1]; best_match is the skill
    string achieving the max (None when requirements is empty).
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be in [0, 1].")
    weights = dict(DEFAULT_CATEGORY_WEIGHTS)
    if category_weights:
        weights.update(category_weights)
    if not facts:
        return []
    fact_texts = [str(f.get("content", "") or "") for f in facts]
    if not requirements:
        return [
            {"index": i, "id": f.get("id"), "section": f.get("section"),
             "content": fact_texts[i], "utility": 0.0, "cosine": 0.0,
             "fuzzy": 0.0, "best_match": None}
            for i, f in enumerate(facts)
        ]
    req_skills = [str(r.get("skill", "") or "") for r in requirements]
    importance = np.array(
        [max(0.0, min(1.0, float(r.get("importance", 1.0)))) for r in requirements],
        dtype=np.float32,
    )
    cat_w = np.array(
        [float(weights.get(str(r.get("category", "required")), 1.0))
         for r in requirements],
        dtype=np.float32,
    )
    cos_mat = cosine_similarity_matrix(
        fact_texts, req_skills,
        fact_embeddings=[_as_array(f.get("embedding")) for f in facts],
        req_embeddings=[_as_array(r.get("embedding")) for r in requirements],
    )
    fuzz_mat = fuzzy_match_matrix(fact_texts, req_skills)
    blended = alpha * cos_mat + (1.0 - alpha) * fuzz_mat
    weighted = blended * (importance * cat_w)[None, :]
    best_j = np.argmax(weighted, axis=1)
    results: List[Dict[str, Any]] = []
    for i, f in enumerate(facts):
        j = int(best_j[i])
        results.append({
            "index": i,
            "id": f.get("id"),
            "section": f.get("section"),
            "content": fact_texts[i],
            "utility": float(weighted[i, j]),
            "cosine": float(cos_mat[i, j]),
            "fuzzy": float(fuzz_mat[i, j]),
            "best_match": req_skills[j],
        })
    logger.info("Scored %d facts vs %d requirements (alpha=%.2f)",
                len(facts), len(requirements), alpha)
    return results
