"""
src/resume_parser.py
Structured resume ingestion for KnapResume.

Takes scraped resume text (from src/parser.py) and parses it into a
normalized structure: profile name, contact block, summary, and per-section
entries (experience/education/projects as job entries, plus free-form
sections such as skills and certifications).

The parsed structure is lowered into a flat fact list suitable for
src/profile_service.ingest_resume(), which persists facts to SQLite
(Stage 1.3 — Document Ingestion).
"""

import re
from typing import Any, Dict, List, Optional

from src.logger import get_logger

logger = get_logger("resume_parser")

# Known section header keywords (mirrors src/pdf_generator.py)
SECTION_KEYWORDS = {
    "summary", "profile", "objective", "about",
    "experience", "work experience", "employment", "career history",
    "education", "academic background", "qualifications",
    "skills", "technical skills", "core competencies", "competencies",
    "certifications", "certificates", "awards", "honours", "honors",
    "projects", "publications", "languages", "interests", "volunteering",
    "references", "professional development", "training",
}

# Section aliases mapped to canonical fact section names
SECTION_ALIASES = {
    "work experience": "experience",
    "employment": "experience",
    "career history": "experience",
    "professional experience": "experience",
    "academic background": "education",
    "qualifications": "education",
    "technical skills": "skills",
    "core competencies": "skills",
    "competencies": "skills",
    "certificates": "certifications",
    "honours": "awards",
    "honors": "awards",
    "objective": "summary",
    "profile": "summary",
    "about": "summary",
}

# Entry-based sections (job entries with heading + bullets)
ENTRY_SECTIONS = {"experience", "education", "projects"}

_BULLET_RE = re.compile(r"^\s*[•\-\*–·]\s+\S")
_JOB_SEP_RE = re.compile(r"\s*[|–—]\s*")
_DATE_ONLY_RE = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4})"
    r".{0,30}(present|current|\d{4})$",
    re.IGNORECASE,
)


def _strip_markdown(line: str) -> str:
    """Remove markdown formatting: ##, **, __, *, _"""
    line = re.sub(r"^#{1,3}\s*", "", line)
    line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
    line = re.sub(r"__(.*?)__", r"\1", line)
    line = re.sub(r"\*(.*?)\*", r"\1", line)
    line = re.sub(r"_(.*?)_", r"\1", line)
    return line.strip()


def _is_section_header(raw: str) -> bool:
    """Detect resume section headers (ALL CAPS or known keywords)."""
    stripped = raw.strip()
    if not stripped or len(stripped) > 60:
        return False
    clean = _strip_markdown(stripped)
    if not clean:
        return False
    if clean.isupper() and 2 < len(clean) < 50:
        return True
    return clean.lower().strip(":").strip() in SECTION_KEYWORDS


def _section_name(raw: str) -> str:
    """Return the canonical fact section name for a header line."""
    clean = _strip_markdown(raw.strip()).strip(":").strip().lower()
    return SECTION_ALIASES.get(clean, clean)


def _is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _clean_bullet(line: str) -> str:
    return _strip_markdown(re.sub(r"^\s*[•\-\*–·]\s*", "", line))


def _is_job_entry(line: str) -> bool:
    """Detect a 'Role | Company | Dates' line."""
    stripped = line.strip()
    if len(stripped) > 120:
        return False
    has_separator = bool(_JOB_SEP_RE.search(stripped))
    has_alpha = bool(re.search(r"[A-Za-z]{3,}", stripped))
    return has_separator and has_alpha


def _split_job_entry(line: str):
    parts = _JOB_SEP_RE.split(line.strip(), maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return line.strip(), ""


def _parse_entry_lines(lines: List[str]) -> List[Dict[str, Any]]:
    """
    Convert raw lines in an entry section into job entries:
      [{"heading": "Role", "meta": "Company | Dates", "bullets": [...]}, ...]
    """
    entries: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if _is_bullet(line):
            if current is None:
                current = {"heading": "", "meta": "", "bullets": []}
                entries.append(current)
            current["bullets"].append(_clean_bullet(line))
            continue
        if _is_job_entry(line):
            heading, meta = _split_job_entry(line)
            current = {"heading": heading, "meta": meta, "bullets": []}
            entries.append(current)
            continue
        if _DATE_ONLY_RE.match(line) and current is not None:
            current["meta"] = (current["meta"] + " | " if current["meta"] else "") + line
            continue
        # Plain line: treat as bold heading if short, else as a bullet
        if current is None:
            current = {"heading": _strip_markdown(line), "meta": "", "bullets": []}
            entries.append(current)
        else:
            current["bullets"].append(_strip_markdown(line))

    return entries


def parse_resume(text: str) -> Dict[str, Any]:
    """
    Parse resume text into a normalized structure.

    Returns:
        {
          "name": str,
          "contact": [str, ...],
          "summary": str,
          "sections": {
              "experience": [{"heading", "meta", "bullets"}, ...],
              "skills": [str, ...],
              ...
          }
        }
    """
    structure = {"name": "", "contact": [], "summary": "", "sections": {}}

    lines = (text or "").split("\n")
    idx = 0

    # Name = first non-empty line
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        return structure
    structure["name"] = _strip_markdown(lines[idx].strip())
    idx += 1

    # Contact block = consecutive non-empty lines until blank or section header
    while idx < len(lines):
        line = lines[idx].strip()
        if not line or _is_section_header(lines[idx]):
            break
        structure["contact"].append(_strip_markdown(line))
        idx += 1

    # Body: group lines under section headers
    current_section: Optional[str] = None
    pending: List[str] = []

    def _finalize():
        if current_section is None or not pending:
            return
        if current_section == "summary":
            structure["summary"] = " ".join(_strip_markdown(l) for l in pending)
            return
        if current_section in ENTRY_SECTIONS:
            structure["sections"][current_section] = _parse_entry_lines(pending)
        else:
            structure["sections"][current_section] = [
                _strip_markdown(l) for l in pending if l.strip()
            ]

    for raw in lines[idx:]:
        line = raw.strip()
        if not line:
            continue
        if _is_section_header(raw):
            _finalize()
            current_section = _section_name(raw)
            pending = []
            continue
        pending.append(line)

    _finalize()

    # Any text before the first header becomes the summary
    if "summary" not in structure["sections"] and not structure["summary"]:
        # No explicit summary: leave empty (caller decides)
        pass

    logger.info(
        "Parsed resume: name=%r contact=%d sections=%s",
        structure["name"], len(structure["contact"]),
        list(structure["sections"].keys()),
    )
    return structure


def to_facts(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Lower a parsed resume structure into discrete fact dicts:
        [{"section", "content", "is_mandatory"}, ...]

    - Contact lines and job entry headings are structural metadata (mandatory).
    - Job entry bullets are optional achievement facts.
    - Free-form section lines are mandatory for certifications/education,
      optional for skills/projects/languages/interests.
    """
    facts: List[Dict[str, Any]] = []

    # Contact block
    for line in structure.get("contact", []):
        facts.append({"section": "contact", "content": line, "is_mandatory": True})

    # Summary
    summary = (structure.get("summary") or "").strip()
    if summary:
        facts.append({"section": "summary", "content": summary, "is_mandatory": True})

    # Sections
    for section, items in structure.get("sections", {}).items():
        if section in ENTRY_SECTIONS:
            for entry in items:
                heading = entry.get("heading", "").strip()
                meta = entry.get("meta", "").strip()
                content = f"{heading} | {meta}" if heading and meta else (heading or meta)
                if content:
                    facts.append({"section": section, "content": content, "is_mandatory": True})
                for bullet in entry.get("bullets", []):
                    facts.append({"section": section, "content": bullet, "is_mandatory": False})
        else:
            mandatory = section in {"certifications", "education", "languages", "summary"}
            for item in items:
                if item.strip():
                    facts.append({"section": section, "content": item, "is_mandatory": mandatory})

    return facts