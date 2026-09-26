"""
src/jd_structuring.py
Stage 2.1 — JD text cleaning & boilerplate filtering (stdlib-only).
Stage 2.2 — KeyBERT keyword extraction + required/nice_to_have split.
Stage 2.3 — Embedding role-type classification + JD/JDRequirement persistence.

Layering:
  - 2.1 (pure): clean_jd_text, extract_company, extract_job_title,
    extract_sections, structure_jd — no models, no DB.
  - 2.2 (models): extract_keywords (KeyBERT over cleaned_text),
    extract_requirements (taxonomy-mapped, cue-split).
  - 2.3 (models + DB): classify_role_type, persist_jd.
Raises ValueError on empty input.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from src.logger import get_logger

logger = get_logger("jd_structuring")

# ── Boilerplate patterns (paragraph-level drop) ──────────────────────────────
# Each pattern matches a full paragraph/sentence that carries no hiring signal.
_BOILERPLATE_RES = [
    # EEO / diversity / inclusion
    re.compile(r"equal\s+opportunity\s+employer", re.IGNORECASE),
    re.compile(r"all\s+qualified\s+applicants?\s+will\s+receive\s+consideration", re.IGNORECASE),
    re.compile(r"without\s+regard\s+to\s+(race|color|religion|sex|gender|age|disability)", re.IGNORECASE),
    re.compile(r"regardless\s+of\s+(race|color|religion|sex|gender|national\s+origin)", re.IGNORECASE),
    re.compile(r"committed\s+to\s+(diversity|inclusion|equity)", re.IGNORECASE),
    re.compile(r"diverse\s+(workforce|workplace|team|backgrounds)", re.IGNORECASE),
    re.compile(r"veteran\s+status|genetic\s+information|sexual\s+orientation", re.IGNORECASE),
    # Legal / compliance / privacy
    re.compile(r"e-?verify|background\s+check|drug\s+(test|screening)", re.IGNORECASE),
    re.compile(r"reasonable\s+accommodation", re.IGNORECASE),
    re.compile(r"privacy\s+(policy|notice)|data\s+protection|gdpr|ccpa", re.IGNORECASE),
    re.compile(r"terms\s+of\s+(use|service)|legal\s+disclaimer", re.IGNORECASE),
    # Promo / benefits / perks paragraphs
    re.compile(r"^(we\s+offer|benefits\s+include|perks\s+include|what\s+we\s+offer)\b", re.IGNORECASE),
    re.compile(r"\b(free\s+lunch|ping-?pong|nap\s+pods|beer\s+fridge)\b", re.IGNORECASE),
]

# Inline EEO sentences that may sit inside an otherwise useful paragraph.
_INLINE_BOILERPLATE_RES = [
    re.compile(r"[^.]*equal\s+opportunity\s+employer[^.]*\.", re.IGNORECASE),
    re.compile(r"[^.]*without\s+regard\s+to\s+[^.]*\.", re.IGNORECASE),
    re.compile(r"[^.]*reasonable\s+accommodation[^.]*\.", re.IGNORECASE),
]

# ── Section headers ──────────────────────────────────────────────────────────
# Canonical section name -> alias header spellings (lowercased, colon-stripped).
_SECTION_ALIASES = {
    "requirements": {"requirements", "requirement", "what you'll need", "what you need",
                     "must have", "must-have", "basic qualifications", "minimum qualifications",
                     "key requirements", "job requirements"},
    "responsibilities": {"responsibilities", "responsibility", "what you'll do",
                         "what you will do", "role responsibilities", "key responsibilities",
                         "duties", "your role", "the role"},
    "qualifications": {"qualifications", "qualification", "who you are", "about you",
                       "ideal candidate", "preferred qualifications", "minimum requirements"},
    "nice_to_have": {"nice to have", "nice-to-have", "nice to haves", "preferred",
                     "preferred skills", "bonus", "bonus points", "pluses", "plus",
                     "desired", "desired skills", "optional", "good to have"},
    "about": {"about us", "about the company", "about the role", "about the team",
              "company overview", "who we are", "why join us"},
    "benefits": {"benefits", "what we offer", "perks", "compensation", "salary",
                 "pay range", "total rewards"},
}

# Reverse lookup: alias -> canonical.
_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for _canon, _aliases in _SECTION_ALIASES.items():
    for _a in _aliases:
        _ALIAS_TO_CANONICAL[_a] = _canon
    _ALIAS_TO_CANONICAL[_canon] = _canon

_KNOWN_HEADERS = set(_ALIAS_TO_CANONICAL.keys())

# Sections whose content is hiring signal (kept in cleaned_text).
_SIGNAL_SECTIONS = {"requirements", "responsibilities", "qualifications", "nice_to_have"}


def _is_section_header(line: str) -> bool:
    """True if a line looks like a JD section header."""
    stripped = line.strip().strip(":").strip()
    if not stripped or len(stripped) > 60:
        return False
    lowered = stripped.lower()
    if lowered in _KNOWN_HEADERS:
        return True
    # ALL-CAPS short headers ("MUST HAVE", "ABOUT US:")
    if stripped.isupper() and 2 < len(stripped) < 50 and len(stripped.split()) <= 5:
        return True
    return False


def _canonical_section(raw: str) -> str:
    lowered = raw.strip().strip(":").strip().lower()
    if lowered in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[lowered]
    # Unknown ALL-CAPS header -> bucket as "other", not signal.
    return "other"


def _split_paragraphs(text: str) -> List[str]:
    """Split on blank lines; fall back to single block."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return parts or ([text.strip()] if (text or "").strip() else [])


def _is_boilerplate_paragraph(para: str) -> bool:
    return any(rx.search(para) for rx in _BOILERPLATE_RES)


def clean_jd_text(text: str) -> str:
    """
    Strip boilerplate paragraphs and inline EEO sentences.

    Returns normalized text (single newlines, collapsed spaces).
    Raises ValueError on empty input.
    """
    if not text or not str(text).strip():
        raise ValueError("JD text must be non-empty.")
    kept: List[str] = []
    for para in _split_paragraphs(str(text)):
        # Line-level filtering: a promo/EEO keyword must only kill its own
        # line, not a whole multi-line paragraph that also holds signal.
        kept_lines: List[str] = []
        for ln in para.split("\n"):
            stripped = ln.strip()
            if not stripped:
                continue
            # Drop non-signal section headers (benefits/about) — Stage 2.2
            # only needs requirement-relevant text; sections stay intact in
            # extract_sections().
            if _is_section_header(stripped):
                canon = _canonical_section(stripped)
                if canon not in _SIGNAL_SECTIONS and canon != "other":
                    continue
            if _is_boilerplate_paragraph(stripped):
                continue
            scrubbed = stripped
            for rx in _INLINE_BOILERPLATE_RES:
                scrubbed = rx.sub(" ", scrubbed)
            scrubbed = re.sub(r"[ \t]+", " ", scrubbed).strip()
            if scrubbed:
                kept_lines.append(scrubbed)
        if kept_lines:
            kept.append("\n".join(kept_lines))
    cleaned = "\n\n".join(kept).strip()
    if not cleaned:
        raise ValueError("JD text contains only boilerplate.")
    logger.info("Cleaned JD: %d -> %d chars (%d paragraphs kept)",
                len(text), len(cleaned), len(kept))
    return cleaned


def extract_company(text: str) -> str:
    """
    Best-effort company extraction. Returns "" when not found
    (callers apply their own fallback label).
    """
    if not text or not str(text).strip():
        return ""
    lines = str(text).split("\n")
    # 1. Explicit labels: "Company: Acme", "Organization: Acme".
    for line in lines[:15]:
        m = re.match(r"\s*(company|organization|employer)\s*[:\-–]\s*(.+)$",
                     line, re.IGNORECASE)
        if m and m.group(2).strip():
            return m.group(2).strip()[:80]
    # 2. "About <Company>" header -> suffix on the same line only.
    # NOTE: generic headers ("About Us", "About the team") are skipped —
    # the next line is a description, not a company name.
    for i, line in enumerate(lines[:15]):
        m = re.match(r"\s*about\s+(.+)$", line.strip(), re.IGNORECASE)
        if m:
            cand = m.group(1).strip().strip("-–: ")
            if cand and cand.lower() not in {"us", "the company", "the role", "the team"}:
                return cand[:80]
            continue
    # 3. Inline "at/for/join <Company>" (same heuristic as app.py/main.py).
    for line in lines[:15]:
        m = re.search(
            r"(?:at|@|for|join|joining)\s+([A-Z][A-Za-z0-9&.\s]{2,40}?)"
            r"(?:\s*[,.|–—]|\s+is\b|\s+we\b|\s+are\b|$)",
            line.strip(),
        )
        if m:
            cand = m.group(1).strip()
            if cand and len(cand) >= 2:
                return cand[:80]
    return ""


def extract_job_title(text: str) -> str:
    """Best-effort role-title extraction. Returns "" when not found."""
    if not text or not str(text).strip():
        return ""
    lines = [ln.strip() for ln in str(text).split("\n")]
    # 1. Explicit labels anywhere in the head.
    for line in lines[:15]:
        m = re.match(r"\s*(job\s*title|position|role|opening|hiring)\s*[:\-–]\s*(.+)$",
                     line, re.IGNORECASE)
        if m and m.group(2).strip():
            return m.group(2).strip()[:80]
        m = re.match(r"\s*hiring\s*[:\-–]?\s*(.+)$", line, re.IGNORECASE)
        if m and m.group(2).strip() and len(m.group(2).strip()) > 3:
            return m.group(2).strip()[:80]
    # 2. First substantial non-company line (skip boilerplate-ish openers).
    for line in lines[:10]:
        if not line or len(line) < 4 or _is_section_header(line):
            continue
        if re.match(r"\s*(company|organization|employer)\s*[:\-–]", line, re.IGNORECASE):
            continue
        if _is_boilerplate_paragraph(line):
            continue
        return line[:80]
    return ""


def extract_sections(text: str) -> Dict[str, List[str]]:
    """
    Group JD lines under canonical section headers.
    Pre-header body goes to "other". Raises ValueError on empty input.
    """
    if not text or not str(text).strip():
        raise ValueError("JD text must be non-empty.")
    sections: Dict[str, List[str]] = {}
    current = "other"
    pending: List[str] = []

    def _flush() -> None:
        if pending:
            sections.setdefault(current, []).extend(pending)

    for raw in str(text).split("\n"):
        line = raw.strip()
        if not line:
            continue
        if _is_section_header(raw):
            _flush()
            current = _canonical_section(raw)
            pending = []
            continue
        pending.append(line)
    _flush()
    logger.info("Extracted JD sections: %s",
                {k: len(v) for k, v in sections.items()})
    return sections


def structure_jd(text: str) -> Dict[str, Any]:
    """
    Full Stage 2.1 pipeline: validate -> extract metadata/sections ->
    cleaned signal text.

    Returns {raw_text, cleaned_text, company, job_title, sections}.
    cleaned_text joins only signal sections (requirements/responsibilities/
    qualifications/nice_to_have); falls back to boilerplate-stripped full
    text when no headers are present.
    """
    if not text or not str(text).strip():
        raise ValueError("JD text must be non-empty.")
    raw = str(text).strip()
    company = extract_company(raw)
    job_title = extract_job_title(raw)
    sections = extract_sections(raw)
    signal_lines: List[str] = []
    for name in ("requirements", "responsibilities", "qualifications", "nice_to_have"):
        signal_lines.extend(sections.get(name, []))
    if signal_lines:
        cleaned_text = clean_jd_text("\n".join(signal_lines))
    else:
        cleaned_text = clean_jd_text(raw)
    return {
        "raw_text": raw,
        "cleaned_text": cleaned_text,
        "company": company,
        "job_title": job_title,
        "sections": sections,
    }


# ── Stage 2.2 — Keyword & skill extraction ────────────────────────────────────

# Curated skill taxonomy (canonical display names). KeyBERT phrases are mapped
# onto these; the taxonomy regex scan also catches skills KeyBERT paraphrases
# away ("docker kafka" bigram hides the individual "Docker"/"Kafka" hits).
SKILL_TAXONOMY = [
    "Python", "Java", "Go", "Rust", "C++", "C#", "JavaScript", "TypeScript",
    "SQL", "Ruby", "PHP", "Swift", "Kotlin", "Scala",
    "React", "Angular", "Vue", "Next.js", "Node.js", "Express",
    "Django", "FastAPI", "Flask", "Spring", ".NET",
    "REST", "GraphQL", "gRPC", "Microservices",
    "HTML", "CSS", "Figma",
    "Postgres", "MySQL", "MongoDB", "Redis", "Elasticsearch",
    "Snowflake", "BigQuery", "Spark", "Kafka", "Airflow", "Hadoop", "dbt",
    "ETL", "Pandas", "NumPy", "Data Warehouse",
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "Helm",
    "Prometheus", "Grafana", "Jenkins", "CI/CD", "Linux", "Bash",
    "PyTorch", "TensorFlow", "scikit-learn", "NLP", "LLM",
    "Machine Learning", "Deep Learning", "Computer Vision", "MLOps",
    "iOS", "Android", "Flutter", "React Native",
    "Agile", "Scrum",
]

_NORMALIZED_SKILLS: Dict[str, str] = {s.lower(): s for s in SKILL_TAXONOMY}

# Line-level cues that mark a requirement as nice-to-have rather than required.
_NICE_CUES_RE = re.compile(
    r"\b(preferred|preferably|bonus|plus\b|pluses|nice\s+to\s+have|good\s+to\s+have"
    r"|desired|optional|familiarity|exposure|ideally|a\s+plus)\b",
    re.IGNORECASE,
)

_EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_kw_model = None
_embed_model = None


def _get_embed_model():
    """Lazy singleton SentenceTransformer (shared by KeyBERT + classifier)."""
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
        logger.info("Loaded embedding model %s", _EMBED_MODEL_NAME)
    return _embed_model


def _get_kw_model():
    """Lazy singleton KeyBERT reusing the shared embedding model."""
    global _kw_model
    if _kw_model is None:
        from keybert import KeyBERT
        _kw_model = KeyBERT(model=_get_embed_model())
        logger.info("Loaded KeyBERT on %s", _EMBED_MODEL_NAME)
    return _kw_model


def _skill_pattern(skill: str) -> "re.Pattern":
    # Custom boundaries: \b breaks on C++/C#/Node.js/CI/CD, so use
    # explicit non-identifier lookarounds instead.
    return re.compile(
        r"(?<![A-Za-z0-9_+#./])" + re.escape(skill) + r"(?![A-Za-z0-9_+#./])",
        re.IGNORECASE,
    )


def _scan_taxonomy_skills(line: str) -> List[str]:
    """All taxonomy skills mentioned in a line (canonical names, order kept)."""
    found: List[str] = []
    for skill in SKILL_TAXONOMY:
        if _skill_pattern(skill).search(line):
            found.append(skill)
    return found


def extract_keywords(text: str, top_n: int = 10) -> List[Tuple[str, float]]:
    """
    KeyBERT unigram + bigram candidates over JD text.
    Returns [(phrase, score)] sorted by score desc. Raises ValueError on empty.
    """
    if not text or not str(text).strip():
        raise ValueError("JD text must be non-empty.")
    if top_n <= 0:
        return []
    model = _get_kw_model()
    pairs = model.extract_keywords(
        str(text),
        keyphrase_ngram_range=(1, 2),
        top_n=top_n,
        use_mmr=True,
        diversity=0.5,
    )
    result = [(str(phrase).strip(), float(score)) for phrase, score in pairs]
    logger.info("KeyBERT extracted %d candidates", len(result))
    return result


def _map_phrase_to_skills(phrase: str) -> List[str]:
    """Map a KeyBERT phrase onto taxonomy skills via substring match."""
    lowered = phrase.lower().strip()
    if lowered in _NORMALIZED_SKILLS:
        return [_NORMALIZED_SKILLS[lowered]]
    hits = [canon for norm, canon in _NORMALIZED_SKILLS.items()
            if norm in lowered or lowered in norm]
    return hits


def extract_requirements(
    text: str,
    sections: Optional[Dict[str, List[str]]] = None,
    top_n: int = 15,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Split JD hiring signal into required vs nice-to-have skills.

    Pipeline: taxonomy scan per signal-section line (cue- and section-aware)
    + KeyBERT discovery mapped onto the taxonomy. Each skill carries
    {skill, importance}. Raises ValueError on empty input.

    importance: taxonomy hits default 0.7 (required) / 0.4 (nice_to_have);
    KeyBERT-mapped skills use min(1.0, 0.4 + score) / score*0.7.
    """
    if not text or not str(text).strip():
        raise ValueError("JD text must be non-empty.")
    raw = str(text)
    if sections is None:
        try:
            sections = extract_sections(raw)
        except ValueError:
            sections = {"other": [raw]}

    # skill -> {"importance", "category"}; required wins on conflict.
    merged: Dict[str, Dict[str, Any]] = {}

    def _upsert(skill: str, category: str, importance: float) -> None:
        importance = max(0.0, min(1.0, float(importance)))
        prev = merged.get(skill)
        if prev is None:
            merged[skill] = {"importance": importance, "category": category}
        elif prev["category"] == "nice_to_have" and category == "required":
            prev["category"] = "required"
            prev["importance"] = max(prev["importance"], importance)
        else:
            prev["importance"] = max(prev["importance"], importance)

    for section in ("requirements", "responsibilities", "qualifications", "nice_to_have"):
        for line in (sections or {}).get(section, []):
            category = ("nice_to_have"
                        if section == "nice_to_have" or _NICE_CUES_RE.search(line)
                        else "required")
            for skill in _scan_taxonomy_skills(line):
                _upsert(skill, category, 0.4 if category == "nice_to_have" else 0.7)

    # KeyBERT discovery over the cleaned signal text (best effort: a model
    # failure must not lose the taxonomy hits above).
    try:
        signal_lines: List[str] = []
        for name in ("requirements", "responsibilities", "qualifications", "nice_to_have"):
            signal_lines.extend((sections or {}).get(name, []))
        kw_text = "\n".join(signal_lines) if signal_lines else raw
        for phrase, score in extract_keywords(kw_text, top_n=top_n):
            for skill in _map_phrase_to_skills(phrase):
                # Taxonomy scan above is authoritative for category (section
                # + cue aware); KeyBERT only discovers NEW skills. Without
                # this guard, a paraphrased phrase ("spark terraform") fails
                # the substring check below and wrongly flips a nice_to_have
                # skill to required.
                if skill in merged:
                    continue
                # Attribute by the sections containing the phrase; fall back
                # to cue words inside the phrase itself.
                in_nice = any(
                    phrase.lower() in ln.lower()
                    for ln in (sections or {}).get("nice_to_have", [])
                )
                category = ("nice_to_have"
                            if in_nice or _NICE_CUES_RE.search(phrase)
                            else "required")
                base = min(1.0, 0.4 + score)
                _upsert(skill, category, base * 0.7 if category == "nice_to_have" else base)
    except Exception as e:
        logger.warning("KeyBERT discovery skipped (%s); taxonomy hits kept", e)

    required = sorted(
        ({"skill": s, "importance": v["importance"]} for s, v in merged.items()
         if v["category"] == "required"),
        key=lambda d: -d["importance"],
    )
    nice = sorted(
        ({"skill": s, "importance": v["importance"]} for s, v in merged.items()
         if v["category"] == "nice_to_have"),
        key=lambda d: -d["importance"],
    )
    logger.info("Requirements: %d required, %d nice_to_have",
                len(required), len(nice))
    return {"required_skills": required, "nice_to_have": nice}


# ── Stage 2.3 — Role-type classification & persistence ────────────────────────

# Fixed role taxonomy: anchor description (embedding) + keyword set (fallback).
ROLE_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "backend": {
        "anchor": "backend engineer building server APIs and microservices with Python Java databases",
        "keywords": {"backend", "python", "java", "go", "node.js", "api", "microservices",
                     "django", "fastapi", "spring", "postgres", "server"},
    },
    "frontend": {
        "anchor": "frontend engineer building user interfaces with React JavaScript TypeScript CSS",
        "keywords": {"frontend", "react", "javascript", "typescript", "css", "html",
                     "vue", "angular", "ui", "next.js"},
    },
    "fullstack": {
        "anchor": "fullstack engineer working across frontend and backend with React Node databases",
        "keywords": {"fullstack", "full-stack", "full stack", "mern", "frontend and backend"},
    },
    "data": {
        "anchor": "data engineer building ETL pipelines and warehouses with Spark SQL Airflow",
        "keywords": {"data engineer", "etl", "spark", "airflow", "pipeline", "warehouse",
                     "snowflake", "bigquery", "dbt", "hadoop"},
    },
    "devops": {
        "anchor": "devops engineer automating infrastructure with Kubernetes Docker Terraform AWS CI/CD",
        "keywords": {"devops", "kubernetes", "docker", "terraform", "ci/cd", "aws",
                     "helm", "prometheus", "sre", "infrastructure"},
    },
    "mobile": {
        "anchor": "mobile engineer building iOS and Android apps with Swift Kotlin Flutter",
        "keywords": {"mobile", "ios", "android", "swift", "kotlin", "flutter", "react native"},
    },
    "ml": {
        "anchor": "machine learning engineer training models with PyTorch TensorFlow LLMs",
        "keywords": {"machine learning", "ml engineer", "pytorch", "tensorflow", "llm",
                     "nlp", "deep learning", "computer vision", "mlops"},
    },
}

# Deterministic title override: matched before embeddings so tests and
# obvious titles never depend on model weights.
_TITLE_ROLE_RES = [
    (re.compile(r"\bfull[-\s]?stack\b", re.IGNORECASE), "fullstack"),
    (re.compile(r"\bfront[-\s]?end\b", re.IGNORECASE), "frontend"),
    (re.compile(r"\bback[-\s]?end\b", re.IGNORECASE), "backend"),
    (re.compile(r"\bdata\s+engineer\b|\bdata\s+scientist\b|\banalytics\s+engineer\b", re.IGNORECASE), "data"),
    (re.compile(r"\bdevops\b|\bsite\s+reliability\b|\bsre\b|\bplatform\s+engineer\b", re.IGNORECASE), "devops"),
    (re.compile(r"\bmobile\b|\bios\b|\bandroid\b", re.IGNORECASE), "mobile"),
    (re.compile(r"\bmachine\s+learning\b|\bml\s+engineer\b|\bai\s+engineer\b|\bdata\s+scientist\b", re.IGNORECASE), "ml"),
]


def classify_role_type(text: str, job_title: str = "") -> str:
    """
    Classify a JD into the fixed role taxonomy. Returns one of
    backend/frontend/fullstack/data/devops/mobile/ml.
    Raises ValueError on empty input.

    Order: explicit title match -> embedding cosine vs anchors ->
    keyword-overlap fallback (model failure path).
    """
    if not text or not str(text).strip():
        raise ValueError("JD text must be non-empty.")
    for rx, role in _TITLE_ROLE_RES:
        if job_title and rx.search(job_title):
            return role
    raw = str(text)
    head = (job_title + "\n" + raw)[:2000] if job_title else raw[:2000]
    try:
        model = _get_embed_model()
        import numpy as np
        anchors = [ROLE_TAXONOMY[r]["anchor"] for r in ROLE_TAXONOMY]
        embs = model.encode([head] + anchors, normalize_embeddings=True)
        sims = np.asarray(embs[0]) @ np.asarray(embs[1:]).T
        best = list(ROLE_TAXONOMY.keys())[int(np.argmax(sims))]
        logger.info("Role classified as %s (cosine=%.3f)", best, float(np.max(sims)))
        return best
    except Exception as e:
        logger.warning("Embedding classification failed (%s); keyword fallback", e)
    lowered = (job_title + "\n" + raw).lower()
    scores = {role: sum(1 for kw in spec["keywords"] if kw in lowered)
              for role, spec in ROLE_TAXONOMY.items()}
    best = max(scores, key=lambda r: (scores[r], r))
    return best if scores[best] > 0 else "backend"


def persist_jd(raw_text: str, session=None) -> Dict[str, Any]:
    """
    Full Stage 2.3 pipeline: structure -> requirements -> role type ->
    persist JD + JDRequirement rows (with skill embeddings for Stage 3).

    Mirrors profile_service's optional-session pattern: pass an in-memory
    session in tests, omit it in production (transactional get_db_session).
    Returns {id, company, job_title, role_type, required_skills,
    nice_to_have, requirements_count}.
    """
    from src.database import get_db_session
    from src.models import JD, JDRequirement

    if not raw_text or not str(raw_text).strip():
        raise ValueError("JD text must be non-empty.")
    struct = structure_jd(str(raw_text))
    reqs = extract_requirements(struct["cleaned_text"], struct["sections"])
    role_type = classify_role_type(struct["cleaned_text"], struct["job_title"])

    def _save(s):
        jd = JD(
            raw_text=struct["raw_text"],
            structured={
                "required_skills": [r["skill"] for r in reqs["required_skills"]],
                "nice_to_have": [r["skill"] for r in reqs["nice_to_have"]],
            },
            role_type=role_type,
            company=struct["company"] or None,
            job_title=struct["job_title"] or None,
        )
        s.add(jd)
        s.flush()
        try:
            model = _get_embed_model()
            vecs = model.encode(
                [r["skill"] for r in reqs["required_skills"] + reqs["nice_to_have"]],
                normalize_embeddings=False,
            )
        except Exception as e:
            logger.warning("Requirement embeddings skipped (%s)", e)
            vecs = [None] * (len(reqs["required_skills"]) + len(reqs["nice_to_have"]))
        for (item, category), vec in zip(
            [(r, "required") for r in reqs["required_skills"]]
            + [(r, "nice_to_have") for r in reqs["nice_to_have"]],
            vecs,
        ):
            row = JDRequirement(
                jd_id=jd.id,
                skill=item["skill"],
                category=category,
                importance=item["importance"],
            )
            if vec is not None:
                import numpy as np
                row.set_embedding(np.asarray(vec, dtype=np.float32))
            s.add(row)
        s.flush()
        logger.info("Persisted JD id=%d role=%s (%d required, %d nice)",
                    jd.id, role_type,
                    len(reqs["required_skills"]), len(reqs["nice_to_have"]))
        return {
            "id": jd.id,
            "company": struct["company"],
            "job_title": struct["job_title"],
            "role_type": role_type,
            "required_skills": [r["skill"] for r in reqs["required_skills"]],
            "nice_to_have": [r["skill"] for r in reqs["nice_to_have"]],
            "requirements_count": len(reqs["required_skills"]) + len(reqs["nice_to_have"]),
        }

    if session is not None:
        return _save(session)
    with get_db_session() as s:
        return _save(s)
