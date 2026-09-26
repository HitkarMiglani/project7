"""
src/claims.py
Stage 4.1 — Claim Extraction & Citation Parser.

Parses LLM-generated tailored text into discrete, testable claims:

    extract_claims(text) -> [{text, cited_fact_ids, raw}]

  - Bullets: lines starting with -, *, •, ·, or ordered markers (1. / 1)).
  - Citations: [F<id>] markers anywhere in the bullet (usually trailing);
    malformed markers ([F], [Fx], [12]) are ignored, not parsed.
  - Continuation lines (non-bullet, non-header, non-empty) join the open
    bullet; section headers and blanks close it.
  - Claim `text` has citation markers stripped and whitespace collapsed;
    empty claims (marker-only bullets) are dropped.
  - Claims citing nothing yield cited_fact_ids=[] — Stage 4.2 treats
    uncited claims as verification suspects, not automatic failures.

Pure + deterministic: no models, no DB access.
"""

import re
from typing import Any, Dict, List

from src.logger import get_logger

logger = get_logger("claims")

CITATION_RE = re.compile(r"\[F(\d+)\]")
# Citation-like noise that carries no fact ID: [F], [Fx], bare [12].
# Stripped from display text but never parsed as citations. Other bracket
# content (e.g. "[Team of 5]") is preserved as real claim text.
_CITATION_NOISE_RE = re.compile(r"\[F[^\d\]]*\]|\[\d+\]")
_BULLET_RE = re.compile(r"^\s*(?:[-*•·]|(?:\d+[.)]))\s+\S")
_BULLET_STRIP_RE = re.compile(r"^\s*(?:[-*•·]|(?:\d+[.)]))\s+")


def _is_section_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    if stripped.endswith(":") and len(stripped.split()) <= 6:
        return True
    return stripped.isupper() and 2 < len(stripped) < 50


def _clean_claim_text(raw: str) -> str:
    text = CITATION_RE.sub(" ", raw)
    text = _CITATION_NOISE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" -–—")


def extract_claims(generated_text: str) -> List[Dict[str, Any]]:
    """
    Split generated resume text into [{text, cited_fact_ids, raw}].
    Empty/whitespace input -> []. Raises ValueError only on non-string input.
    """
    if generated_text is None or not isinstance(generated_text, str):
        raise ValueError("generated_text must be a string.")
    if not generated_text.strip():
        return []
    bullets: List[str] = []
    current: List[str] = []

    def _flush() -> None:
        if current:
            bullets.append(" ".join(current).strip())
            current.clear()

    for line in generated_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            _flush()
            continue
        if _BULLET_RE.match(line):
            _flush()
            current.append(_BULLET_STRIP_RE.sub("", line).strip())
        elif _is_section_header(line):
            _flush()
        elif current:
            current.append(stripped)  # continuation of open bullet
        # Pre-header prose with no open bullet is ignored (contact/name lines).
    _flush()

    claims: List[Dict[str, Any]] = []
    for raw in bullets:
        ids = sorted({int(m) for m in CITATION_RE.findall(raw)})
        text = _clean_claim_text(raw)
        if not text:
            continue  # marker-only bullet carries no claim
        claims.append({"text": text, "cited_fact_ids": ids, "raw": raw})
    logger.info("Extracted %d claims (%d uncited)",
                len(claims), sum(1 for c in claims if not c["cited_fact_ids"]))
    return claims
