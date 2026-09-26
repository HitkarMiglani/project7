"""
tests/test_pdf_generator.py
PDF formatting fixes: XML escaping, Unicode→ASCII normalization,
section-header guards, fence handling, identifier-safe markdown.

Round-trips representative LLM output through generate_*_pdf and asserts
on pdfplumber-extracted text (the same surface the user reads).
"""

import pytest

pdfplumber = pytest.importorskip("pdfplumber")

from src.pdf_generator import (
    _is_section_header,
    _normalize_text,
    _parse_resume_to_flowables,
    _build_styles,
    generate_cover_letter_pdf,
    generate_resume_pdf,
)
from reportlab.platypus import KeepTogether


LLM_STYLE_RESUME = """John Doe
john@example.com | R&D Engineer at Q&A Corp

## Summary
Backend engineer with 5 < 10 years of focus & "shipping" <products>.

EXPERIENCE
STAFF ENGINEER | ACME CORP | 2021 - PRESENT
- Built Python microservices & cut p95 latency 40%
• Mentored 4 engineers; always — on call
2021 - PRESENT

SKILLS
Python, C/C++, my_variable, **Postgres**, `Docker`
"""


def _extract(path):
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


# ── Round-trip: content survival ─────────────────────────────────────────────

def test_markup_chars_survive_roundtrip(tmp_path):
    out = tmp_path / "resume.pdf"
    generate_resume_pdf(LLM_STYLE_RESUME, str(out))
    text = _extract(out)
    assert "R&D Engineer at Q&A Corp" in text  # & not mangled
    assert "<products>" in text  # angle tags not eaten as XML
    assert "5 < 10" in text
    assert "my_variable" in text  # underscores intact
    assert "Postgres" in text and "Docker" in text  # md stripped, words kept


def test_no_broken_glyphs_in_output(tmp_path):
    out = tmp_path / "resume.pdf"
    generate_resume_pdf(LLM_STYLE_RESUME, str(out))
    text = _extract(out)
    assert "(cid:" not in text  # unmapped bullet glyph
    assert "�" not in text  # replacement chars
    # Bullets render as ASCII dashes, dashes normalized.
    assert "- Built Python microservices" in text
    assert "always - on call" in text


def test_job_entry_split_and_date_line(tmp_path):
    out = tmp_path / "resume.pdf"
    generate_resume_pdf(LLM_STYLE_RESUME, str(out))
    text = _extract(out)
    assert "STAFF ENGINEER" in text
    assert "ACME CORP | 2021 - PRESENT" in text
    assert "2021 - PRESENT" in text  # standalone date line kept as plain line


def test_fences_and_preamble_dropped(tmp_path):
    out = tmp_path / "resume.pdf"
    generate_resume_pdf("```\nJohn Doe\n\nSKILLS\nPython\n```", str(out))
    assert "```" not in _extract(out)


def test_cover_letter_roundtrip(tmp_path):
    out = tmp_path / "cover.pdf"
    generate_cover_letter_pdf(
        "Dear Hiring Team,\n\nI love R&D & shipping <products> — really.\n\nSincerely,\nJohn",
        str(out))
    text = _extract(out)
    assert "R&D & shipping <products> - really." in text


# ── Unit guards ──────────────────────────────────────────────────────────────

def test_header_guard_date_and_job_entry():
    assert _is_section_header("2021 - PRESENT") is False
    assert _is_section_header("STAFF ENGINEER | ACME CORP") is False
    assert _is_section_header("EXPERIENCE") is True
    assert _is_section_header("## Skills") is True


def test_normalize_punctuation():
    assert _normalize_text("a–b—c•d·e“f”‘g’…") == "a-b-c-d-e\"f\"'g'..."
    assert _normalize_text("Café") == "Café"  # Latin-1 accents preserved


def test_section_header_kept_with_rule():
    story = _parse_resume_to_flowables("Name\n\nEXPERIENCE\n- Did x\n",
                                       _build_styles())
    keepers = [f for f in story if isinstance(f, KeepTogether)]
    assert len(keepers) == 1  # header + HR travel together
