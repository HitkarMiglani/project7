"""
src/verifier.py
Stage 4.2 — Hybrid Verification Pipeline.
Stage 4.3 — Hallucination Blocking & Output Sanitization.

Three-state claim verification (Verified / Inferred / Unsupported):

    cosine(claim, facts) >= 0.85            -> Verified   (fast path)
    cosine(claim, facts) <= 0.60            -> Unsupported (fast path)
    0.60 < cosine < 0.85                    -> NLI cross-encoder
        entailment  -> Verified
        neutral     -> Inferred
        contradiction -> Unsupported

  - Cosine uses the shared all-MiniLM-L6-v2 singleton (same vectors as
    scoring); NLI uses cross-encoder/nli-MiniLM2-L6-H768 (~90MB, lazy).
  - Cited facts are checked first; uncited claims are screened against ALL
    facts (near-verbatim copies still verify; fabrications bottom out).
  - NLI failure falls back to a cosine midpoint rule (borderline high ->
    Inferred, else Unsupported) so verification never hard-crashes.
  - 4.3: sanitize_text() drops Unsupported bullets from generated text;
    record_claims() persists results to the claims table.

Pure + deterministic except model inference (deterministic given weights).
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.logger import get_logger

logger = get_logger("verifier")

VERIFIED_THRESHOLD = 0.85
UNSUPPORTED_THRESHOLD = 0.60
# Cosine midpoint used ONLY when the NLI model cannot load.
FALLBACK_INFERRED_THRESHOLD = 0.72
NLI_MODEL_NAME = "cross-encoder/nli-MiniLM2-L6-H768"
# CrossEncoder label order for the MiniLM2 NLI checkpoint.
_NLI_LABELS = ("contradiction", "entailment", "neutral")

_nli_model = None


def _get_nli_model():
    """Lazy singleton NLI cross-encoder."""
    global _nli_model
    if _nli_model is None:
        from sentence_transformers import CrossEncoder
        _nli_model = CrossEncoder(NLI_MODEL_NAME)
        logger.info("Loaded NLI model %s", NLI_MODEL_NAME)
    return _nli_model


def _as_array(vec: Any) -> Optional[np.ndarray]:
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float32).ravel()
    return arr if arr.size else None


def cosine_to_facts(
    claim_text: str,
    facts: List[Dict[str, Any]],
) -> Tuple[float, Optional[Dict[str, Any]]]:
    """
    Best cosine similarity of a claim against fact contents.
    Returns (score in [0, 1], best fact dict or None).
    """
    if not facts:
        return 0.0, None
    from src.jd_structuring import _get_embed_model
    model = _get_embed_model()
    texts = [str(f.get("content", "") or "") or " " for f in facts]
    vecs = [ _as_array(f.get("embedding")) for f in facts]
    if all(v is not None for v in vecs):
        mat = np.stack(vecs).astype(np.float32)
    else:
        mat = np.asarray(
            model.encode(texts + [claim_text or " "],
                         normalize_embeddings=True), dtype=np.float32)
        claim_vec = mat[-1]
        mat = mat[:-1]
        norms = np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9)
        return float(np.clip((mat / norms) @ claim_vec, 0.0, 1.0).max()), \
            facts[int(np.argmax((mat / norms) @ claim_vec))]
    claim_vec = np.asarray(
        model.encode([claim_text or " "], normalize_embeddings=True),
        dtype=np.float32)[0]
    norms = np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9)
    sims = np.clip((mat / norms) @ (claim_vec / max(np.linalg.norm(claim_vec), 1e-9)),
                   0.0, 1.0)
    best = int(np.argmax(sims))
    return float(sims[best]), facts[best]


def nli_judge(claim_text: str, fact_text: str) -> Dict[str, Any]:
    """
    NLI entailment check (premise=fact, hypothesis=claim).
    Returns {label, probabilities: {contradiction, entailment, neutral}}.
    """
    model = _get_nli_model()
    logits = np.asarray(
        model.predict([(fact_text, claim_text)]), dtype=np.float64)[0]
    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()
    best = int(np.argmax(probs))
    return {"label": _NLI_LABELS[best],
            "probabilities": {label: float(probs[i])
                              for i, label in enumerate(_NLI_LABELS)}}


def verify_claim(
    claim: Dict[str, Any],
    facts: List[Dict[str, Any]],
    use_nli: bool = True,
) -> Dict[str, Any]:
    """
    Verify one claim ({text, cited_fact_ids?}) against facts
    ([{id, content, embedding?}]). Returns {text, state, score,
    cited_fact_id, method} with state in verified/inferred/unsupported.
    """
    text = str(claim.get("text", "") or "")
    by_id = {f.get("id"): f for f in facts if f.get("id") is not None}
    cited_ids = [i for i in (claim.get("cited_fact_ids") or []) if i in by_id]
    candidates = [by_id[i] for i in cited_ids] if cited_ids else list(facts)
    if not text.strip() or not candidates:
        return {"text": text, "state": "unsupported", "score": 0.0,
                "cited_fact_id": cited_ids[0] if cited_ids else None,
                "method": "no-evidence",
                **({"raw": claim["raw"]} if "raw" in claim else {})}
    score, best = cosine_to_facts(text, candidates)
    cited_fact_id = (best.get("id") if best else None)
    base = {"text": text, "cited_fact_id": cited_fact_id,
            **({"raw": claim["raw"]} if "raw" in claim else {})}
    if score >= VERIFIED_THRESHOLD:
        return {**base, "state": "verified", "score": score, "method": "cosine"}
    if score <= UNSUPPORTED_THRESHOLD:
        return {**base, "state": "unsupported", "score": score, "method": "cosine"}
    if use_nli:
        try:
            judgement = nli_judge(
                text, str((best or {}).get("content", "") or ""))
            label = judgement["label"]
            probs = judgement["probabilities"]
            if label == "entailment":
                return {**base, "state": "verified",
                        "score": probs["entailment"], "method": "nli-entailment"}
            if label == "neutral":
                return {**base, "state": "inferred",
                        "score": probs["neutral"], "method": "nli-neutral"}
            return {**base, "state": "unsupported",
                    "score": probs["contradiction"],
                    "method": "nli-contradiction"}
        except Exception as e:
            logger.warning("NLI check failed (%s); cosine fallback", e)
    state = ("inferred" if score >= FALLBACK_INFERRED_THRESHOLD
             else "unsupported")
    return {**base, "state": state, "score": score, "method": "cosine-fallback"}


def verify_claims(
    claims: List[Dict[str, Any]],
    facts: List[Dict[str, Any]],
    use_nli: bool = True,
) -> List[Dict[str, Any]]:
    """Verify every claim; returns results in input order."""
    results = [verify_claim(c, facts, use_nli=use_nli) for c in (claims or [])]
    counts = {s: sum(1 for r in results if r["state"] == s)
              for s in ("verified", "inferred", "unsupported")}
    logger.info("Verified %d claims: %s", len(results), counts)
    return results


# ── Stage 4.3 — sanitization & persistence ────────────────────────────────────

def _normalize(line: str) -> str:
    import re
    text = re.sub(r"^\s*(?:[-*•·]|(?:\d+[.)]))\s+", "", line.strip())
    return re.sub(r"\s+", " ", text).strip().lower()


def sanitize_text(
    generated_text: str,
    verified: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Drop Unsupported bullets (plus their continuation lines) from generated
    text. Returns {sanitized_text, blocked: [claim texts], kept_count}.
    Headers, blanks, and verified/inferred bullets are preserved verbatim.
    """
    blocked_raws = {_normalize(str(v.get("raw", "") or ""))
                    for v in verified if v.get("state") == "unsupported"}
    blocked_raws.discard("")
    blocked_texts = [str(v.get("text", "")) for v in verified
                     if v.get("state") == "unsupported"]
    if not blocked_raws:
        return {"sanitized_text": generated_text,
                "blocked": blocked_texts, "kept_count": len(verified)}
    import re as _re
    bullet_re = _re.compile(r"^\s*(?:[-*•·]|(?:\d+[.)]))\s+\S")

    def _is_header(line: str) -> bool:
        s = line.strip()
        return bool(s) and ((s.endswith(":") and len(s.split()) <= 6)
                            or (s.isupper() and 2 < len(s) < 50))

    kept_lines: List[str] = []
    dropping = False
    for line in (generated_text or "").split("\n"):
        s = line.strip()
        if not s:
            dropping = False
            kept_lines.append(line)
        elif bullet_re.match(line):
            norm = _normalize(line)
            drop = any(norm == b or norm in b or b in norm for b in blocked_raws)
            dropping = drop
            if not drop:
                kept_lines.append(line)
        elif _is_header(line):
            dropping = False
            kept_lines.append(line)
        else:
            if not dropping:
                kept_lines.append(line)
    sanitized = "\n".join(kept_lines)
    kept = len(verified) - len(blocked_texts)
    logger.info("Sanitized text: blocked %d unsupported claims", len(blocked_texts))
    return {"sanitized_text": sanitized, "blocked": blocked_texts,
            "kept_count": kept}


def record_claims(
    run_log_id: int,
    verified: List[Dict[str, Any]],
    session=None,
) -> List[Dict[str, Any]]:
    """
    Persist verification results to the claims table. Returns the created
    Claim dicts. Raises ValueError when the run log does not exist.
    """
    from src.database import get_db_session
    from src.models import Claim, RunLog

    def _save(s):
        run = s.query(RunLog).filter(RunLog.id == run_log_id).first()
        if run is None:
            raise ValueError(f"RunLog {run_log_id} not found.")
        out: List[Dict[str, Any]] = []
        for v in verified or []:
            row = Claim(
                run_log_id=run_log_id,
                text=str(v.get("text", "") or ""),
                state=str(v.get("state", "unsupported")),
                score=(float(v["score"]) if v.get("score") is not None else None),
                cited_fact_id=v.get("cited_fact_id"),
            )
            s.add(row)
            s.flush()
            out.append(row.to_dict())
        logger.info("Recorded %d claims for run %d", len(out), run_log_id)
        return out

    if session is not None:
        return _save(session)
    with get_db_session() as s:
        return _save(s)
