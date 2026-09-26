"""
src/profile_service.py
Profile & Fact CRUD service layer for KnapResume.

Provides creation, retrieval, update, and deletion of profiles and their
discrete facts, with:
  - binary float32 vector embedding (de)serialization,
  - base-metadata vs optional-achievement tagging via is_mandatory,
  - optional caller-provided session for testability (in-memory SQLite).

All public functions return plain dicts (via Model.to_dict()) and raise
ProfileNotFoundError / FactNotFoundError / ValueError on invalid input.
"""

import re
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from src.database import get_db_session
from src.logger import get_logger
from src.models import Profile, ProfileFact

logger = get_logger("profile_service")

# Section names whose contents are structural metadata (never dropped by allocator)
STRUCTURAL_SECTIONS = {
    "contact", "name", "header", "basic", "meta", "summary",
    "education", "degree", "certification", "certifications",
    "languages",
}

# Date/contact patterns used to auto-detect structural (metadata) facts
_NOMINAL_PATTERN = re.compile(
    r"^\s*("
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}"
    r"\s*[-–]\s*(present|current|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}|\d{4})"
    r"|\d{4}\s*[-–]\s*(present|current|\d{4})"                    # 2020 - Present
    r"|[\w.+-]+@[\w.-]+\.[a-z]{2,}"                              # email
    r"|(\+?\d[\d\s().-]{7,})"                                    # phone
    r"|(?:https?://)?linkedin\.com/[A-Za-z0-9_/-]+"              # linkedin URL
    r"|(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_.-]+"      # github URL
    r")\s*$",
    re.IGNORECASE,
)


class ProfileNotFoundError(ValueError):
    """Raised when a profile id does not exist."""


class FactNotFoundError(ValueError):
    """Raised when a fact id does not exist."""


def _with_session(session, fn: Callable[[Any], Any]):
    """
    Run fn with a usable session. If session is None, opens a transactional
    scope via get_db_session() (which commits on success / rolls back on error);
    otherwise runs against the caller-provided session (testability path).
    """
    if session is not None:
        return fn(session)
    with get_db_session() as s:
        return fn(s)


def _validate_profile_id(session, profile_id: int) -> Profile:
    profile = session.query(Profile).filter(Profile.id == profile_id).first()
    if profile is None:
        raise ProfileNotFoundError(f"Profile {profile_id} not found.")
    return profile


def _validate_fact(session, fact_id: int) -> ProfileFact:
    fact = session.query(ProfileFact).filter(ProfileFact.id == fact_id).first()
    if fact is None:
        raise FactNotFoundError(f"Fact {fact_id} not found.")
    return fact


def infer_is_mandatory(section: str, content: str) -> bool:
    """
    Heuristically tag whether a fact is base metadata (mandatory) or an
    optional achievement bullet.

    Structural metadata sections (contact, name, education, certifications)
    or content that is purely a date range / contact detail are mandatory.
    Everything else (experience/project achievements) is optional.
    """
    s = (section or "").strip().lower()
    if s in STRUCTURAL_SECTIONS:
        return True
    if _NOMINAL_PATTERN.match(content or ""):
        return True
    return False


# ── Profile CRUD ─────────────────────────────────────────────────────────────

def create_profile(
    name: str = "Default Profile",
    sections: Optional[Dict[str, Any]] = None,
    session=None,
) -> Dict[str, Any]:
    """Create a new profile. Returns the created profile as a dict."""
    if not name or not str(name).strip():
        raise ValueError("Profile name must be non-empty.")

    def _create(s):
        profile = Profile(name=str(name).strip(), sections=sections or {})
        s.add(profile)
        s.flush()
        logger.info("Created profile id=%d name=%r", profile.id, profile.name)
        return profile.to_dict()

    return _with_session(session, _create)


def get_profile(profile_id: int, session=None) -> Dict[str, Any]:
    """Return a profile dict by id. Raises ProfileNotFoundError if missing."""
    def _get(s):
        profile = _validate_profile_id(s, profile_id)
        logger.debug("Fetched profile id=%d", profile_id)
        return profile.to_dict()

    return _with_session(session, _get)


def list_profiles(session=None) -> List[Dict[str, Any]]:
    """Return all profiles, ordered by id."""
    def _list(s):
        profiles = s.query(Profile).order_by(Profile.id).all()
        return [p.to_dict() for p in profiles]

    return _with_session(session, _list)


def update_profile(
    profile_id: int,
    name: Optional[str] = None,
    sections: Optional[Dict[str, Any]] = None,
    session=None,
) -> Dict[str, Any]:
    """Update a profile's name and/or sections. Returns the updated dict."""
    def _update(s):
        profile = _validate_profile_id(s, profile_id)
        if name is not None:
            if not str(name).strip():
                raise ValueError("Profile name must be non-empty.")
            profile.name = str(name).strip()
        if sections is not None:
            profile.sections = sections
        s.flush()
        logger.info("Updated profile id=%d", profile_id)
        return profile.to_dict()

    return _with_session(session, _update)


def delete_profile(profile_id: int, session=None) -> None:
    """Delete a profile and all of its facts (cascade)."""
    def _delete(s):
        profile = _validate_profile_id(s, profile_id)
        fact_count = len(profile.facts) if profile.facts else 0
        s.delete(profile)
        s.flush()
        logger.info("Deleted profile id=%d (removed %d facts)", profile_id, fact_count)

    return _with_session(session, _delete)


# ── Fact CRUD ────────────────────────────────────────────────────────────────

def add_fact(
    profile_id: int,
    section: str,
    content: str,
    is_mandatory: Optional[bool] = None,
    embedding: Optional[np.ndarray] = None,
    session=None,
) -> Dict[str, Any]:
    """
    Add a discrete fact to a profile.

    is_mandatory defaults to infer_is_mandatory(section, content).
    embedding may be a 1-D float32-convertible NumPy array (serialized to
    raw binary buffer via ProfileFact.set_embedding).
    """
    if not section or not str(section).strip():
        raise ValueError("Fact section must be non-empty.")
    if not content or not str(content).strip():
        raise ValueError("Fact content must be non-empty.")

    def _add(s):
        _validate_profile_id(s, profile_id)
        mandatory = (
            infer_is_mandatory(section, content)
            if is_mandatory is None
            else bool(is_mandatory)
        )
        fact = ProfileFact(
            profile_id=profile_id,
            section=str(section).strip(),
            content=str(content).strip(),
            is_mandatory=mandatory,
        )
        if embedding is not None:
            fact.set_embedding(embedding)
        s.add(fact)
        s.flush()
        logger.info(
            "Added fact id=%d to profile id=%d section=%r mandatory=%s has_embedding=%s",
            fact.id, profile_id, fact.section, fact.is_mandatory,
            fact.embedding is not None,
        )
        return fact.to_dict()

    return _with_session(session, _add)


def get_fact(fact_id: int, session=None) -> Dict[str, Any]:
    """Return a single fact dict by id. Raises FactNotFoundError if missing."""
    def _get(s):
        fact = _validate_fact(s, fact_id)
        logger.debug("Fetched fact id=%d", fact_id)
        return fact.to_dict()

    return _with_session(session, _get)


def get_fact_embedding(fact_id: int, session=None) -> Optional[np.ndarray]:
    """Deserialize and return a fact's float32 embedding vector (or None)."""
    def _get(s):
        fact = _validate_fact(s, fact_id)
        return fact.get_embedding()

    return _with_session(session, _get)


def list_facts(
    profile_id: int,
    section: Optional[str] = None,
    session=None,
) -> List[Dict[str, Any]]:
    """List a profile's facts, optionally filtered by section."""
    def _list(s):
        _validate_profile_id(s, profile_id)
        query = s.query(ProfileFact).filter(ProfileFact.profile_id == profile_id)
        if section:
            query = query.filter(ProfileFact.section == str(section).strip())
        facts = query.order_by(ProfileFact.id).all()
        return [f.to_dict() for f in facts]

    return _with_session(session, _list)


def update_fact(
    fact_id: int,
    section: Optional[str] = None,
    content: Optional[str] = None,
    is_mandatory: Optional[bool] = None,
    embedding: Optional[np.ndarray] = None,
    session=None,
) -> Dict[str, Any]:
    """
    Update a fact's section, content, or mandatory flag.
    embedding, when provided, overwrites the stored vector.
    """
    def _update(s):
        fact = _validate_fact(s, fact_id)
        if content is not None:
            if not str(content).strip():
                raise ValueError("Fact content must be non-empty.")
            fact.content = str(content).strip()
        if section is not None:
            if not str(section).strip():
                raise ValueError("Fact section must be non-empty.")
            fact.section = str(section).strip()
        if is_mandatory is not None:
            fact.is_mandatory = bool(is_mandatory)
        if embedding is not None:
            fact.set_embedding(embedding)
        s.flush()
        logger.info("Updated fact id=%d", fact_id)
        return fact.to_dict()

    return _with_session(session, _update)


def clear_fact_embedding(fact_id: int, session=None) -> Dict[str, Any]:
    """Remove a fact's stored embedding vector."""
    def _clear(s):
        fact = _validate_fact(s, fact_id)
        fact.set_embedding(None)
        s.flush()
        logger.info("Cleared embedding on fact id=%d", fact_id)
        return fact.to_dict()

    return _with_session(session, _clear)


def delete_fact(fact_id: int, session=None) -> None:
    """Delete a single fact."""
    def _delete(s):
        fact = _validate_fact(s, fact_id)
        s.delete(fact)
        s.flush()
        logger.info("Deleted fact id=%d", fact_id)

    return _with_session(session, _delete)


# ── Resume ingestion ─────────────────────────────────────────────────────────

def ingest_resume(
    profile_id: int,
    text: str,
    session=None,
) -> Dict[str, Any]:
    """
    Parse structured resume text and persist all extracted content as facts
    on an existing profile (Stage 1.3 — Document Ingestion).

    Uses src.resume_parser.to_facts() to lower the resume into discrete,
    mandatory/optional facts, then persists them via add_fact().
    Does NOT create a new profile; the caller supplies the target profile_id.

    Returns:
        {"profile_id", "facts_created", "sections": {section: count}, "name": str}
    """
    from src.resume_parser import parse_resume, to_facts

    if not text or not str(text).strip():
        raise ValueError("Resume text must be non-empty.")

    structure = parse_resume(str(text))

    def _ingest(s):
        _validate_profile_id(s, profile_id)
        facts = to_facts(structure)
        counts: Dict[str, int] = {}
        for f in facts:
            fact = ProfileFact(
                profile_id=profile_id,
                section=f["section"],
                content=f["content"],
                is_mandatory=f["is_mandatory"],
            )
            s.add(fact)
            counts[f["section"]] = counts.get(f["section"], 0) + 1
        s.flush()
        logger.info(
            "Ingested resume into profile id=%d: %d facts across %d sections",
            profile_id, len(facts), len(counts),
        )
        return {
            "profile_id": profile_id,
            "name": structure.get("name", ""),
            "facts_created": len(facts),
            "sections": counts,
            "summary_chars": len(structure.get("summary", "")),
        }

    return _with_session(session, _ingest)


def ingest_document(
    profile_id: int,
    source,
    filename: str = "",
    session=None,
) -> Dict[str, Any]:
    """
    Extract text from an uploaded document (path, bytes, or plain text string),
    parse it into structured sections, and persist all facts onto a profile.

    This is the Stage 1.3 auto-population entry point used by the upload API.

    Args:
        profile_id: Target profile id.
        source: File path, bytes buffer, or already-extracted plain text.
        filename: Original filename (used for type detection of bytes sources).

    Returns:
        The same dict as ingest_resume().
    """
    from src.parser import extract_text

    try:
        text = extract_text(source, filename)
    except Exception as e:
        logger.warning("Text extraction failed for source=%r filename=%r: %s", source, filename, e)
        raise ValueError(f"Could not extract text: {e}") from e
    return ingest_resume(profile_id, text, session=session)