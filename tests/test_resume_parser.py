"""
tests/test_resume_parser.py
Unit tests for structured resume ingestion (Stage 1.3):
parse_resume structure extraction, to_facts lowering, and
profile_service.ingest_resume / ingest_document auto-population.
"""

import io

import pytest

from src.resume_parser import parse_resume, to_facts
from src.profile_service import (
    ProfileNotFoundError,
    create_profile,
    ingest_document,
    ingest_resume,
    list_facts,
)


SAMPLE_RESUME = """\
Alice Developer
alice@example.com | +1 (555) 123-4567 | github.com/alice

SUMMARY
Backend engineer with 6 years building distributed systems in Python.

EXPERIENCE
Staff Engineer | Acme Corp | 2021 - Present
• Led migration of monolith to microservices, cutting p95 latency 40%
• Mentor 4 engineers; drive quarterly roadmap

Senior Software Engineer | DataWorks | 2018 - 2021
• Built ETL pipelines in Spark serving 2M users
• Improved deployment turnaround from days to hours

EDUCATION
M.S. Computer Science | MIT | 2015 - 2017
B.S. Computer Science | State University | 2011 - 2015

SKILLS
Python, FastAPI, SQL, Docker, Kafka, Spark

CERTIFICATIONS
AWS Solutions Architect - Associate
"""


# ── parse_resume: structure extraction ───────────────────────────────────────

def test_parse_resume_name_contact_summary():
    s = parse_resume(SAMPLE_RESUME)
    assert s["name"] == "Alice Developer"
    assert s["contact"] == ["alice@example.com | +1 (555) 123-4567 | github.com/alice"]
    assert "Backend engineer" in s["summary"]


def test_parse_resume_section_headers():
    s = parse_resume(SAMPLE_RESUME)
    assert set(s["sections"].keys()) == {"experience", "education", "skills", "certifications"}


def test_parse_resume_iterates_experience_entries():
    s = parse_resume(SAMPLE_RESUME)
    exp = s["sections"]["experience"]
    assert len(exp) == 2
    assert exp[0]["heading"] == "Staff Engineer"
    assert exp[0]["meta"] == "Acme Corp | 2021 - Present"
    assert exp[0]["bullets"] == [
        "Led migration of monolith to microservices, cutting p95 latency 40%",
        "Mentor 4 engineers; drive quarterly roadmap",
    ]
    assert exp[1]["heading"] == "Senior Software Engineer"


def test_parse_resume_contains_education_entries():
    s = parse_resume(SAMPLE_RESUME)
    edu = s["sections"]["education"]
    assert len(edu) == 2
    assert edu[0]["heading"] == "M.S. Computer Science"


def test_parse_resume_handles_contact_and_empty_text():
    assert parse_resume("")["name"] == ""
    assert parse_resume("   \n  \n")["name"] == ""
    assert parse_resume("Name only\n")["name"] == "Name only"


def test_parse_resume_section_alias_mapping():
    text = "Jane\njane@x.io\n\nWORK EXPERIENCE\nEngineer | Co | 2020 - Now\n• Did things"
    s = parse_resume(text)
    assert "experience" in s["sections"]


# ── to_facts: fact lowering ──────────────────────────────────────────────────

def test_to_facts_contact_and_summary_mandatory():
    facts = to_facts(parse_resume(SAMPLE_RESUME))
    contacts = [f for f in facts if f["section"] == "contact"]
    summaries = [f for f in facts if f["section"] == "summary"]
    assert contacts and all(f["is_mandatory"] is True for f in contacts)
    assert summaries and all(f["is_mandatory"] is True for f in summaries)


def test_to_facts_entry_headings_mandatory_bullets_optional():
    facts = to_facts(parse_resume(SAMPLE_RESUME))
    exp = [f for f in facts if f["section"] == "experience"]
    headings = [f for f in exp if f["is_mandatory"] is True]
    bullets = [f for f in exp if f["is_mandatory"] is False]
    assert len(headings) == 2
    assert len(bullets) == 4
    assert headings[0]["content"] == "Staff Engineer | Acme Corp | 2021 - Present"


def test_to_facts_skills_optional_certifications_mandatory():
    facts = to_facts(parse_resume(SAMPLE_RESUME))
    skills = [f for f in facts if f["section"] == "skills"]
    certs = [f for f in facts if f["section"] == "certifications"]
    assert skills and all(f["is_mandatory"] is False for f in skills)
    assert certs and all(f["is_mandatory"] is True for f in certs)


# ── ingest_resume: persistence into profile ──────────────────────────────────

def test_ingest_resume_persists_facts(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    result = ingest_resume(profile["id"], SAMPLE_RESUME, session=in_memory_db)
    assert result["profile_id"] == profile["id"]
    assert result["facts_created"] > 5
    assert result["sections"]["experience"] == 6  # 2 headings + 4 bullets

    facts = list_facts(profile["id"], session=in_memory_db)
    sections = {f["section"] for f in facts}
    assert {"contact", "summary", "experience", "education", "skills", "certifications"} <= sections


def test_ingest_resume_empty_text_raises(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    with pytest.raises(ValueError):
        ingest_resume(profile["id"], "   ", session=in_memory_db)


def test_ingest_resume_missing_profile_raises(in_memory_db):
    with pytest.raises(ProfileNotFoundError):
        ingest_resume(99999, SAMPLE_RESUME, session=in_memory_db)


def test_ingest_resume_is_idempotent_across_calls(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    ingest_resume(profile["id"], SAMPLE_RESUME, session=in_memory_db)
    ingest_resume(profile["id"], SAMPLE_RESUME, session=in_memory_db)
    assert len(list_facts(profile["id"], session=in_memory_db)) == 2 * len(
        to_facts(parse_resume(SAMPLE_RESUME))
    )


# ── ingest_document: file / bytes ingestion ──────────────────────────────────

def test_ingest_document_txt_string(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    result = ingest_document(profile["id"], SAMPLE_RESUME, filename="resume.txt", session=in_memory_db)
    assert result["facts_created"] > 0


def test_ingest_document_docx_bytes(in_memory_db):
    from docx import Document

    doc = Document()
    doc.add_paragraph("Bob Engineer")
    doc.add_paragraph("bob@example.com")
    doc.add_paragraph("")
    doc.add_paragraph("SUMMARY")
    doc.add_paragraph("DevOps engineer specializing in Kubernetes.")
    doc.add_paragraph("")
    doc.add_paragraph("SKILLS")
    doc.add_paragraph("Kubernetes, Helm, Terraform, Prometheus")

    buf = io.BytesIO()
    doc.save(buf)
    payload = buf.getvalue()

    profile = create_profile(name="Bob", session=in_memory_db)
    result = ingest_document(profile["id"], payload, filename="resume.docx", session=in_memory_db)
    assert result["name"] == "Bob Engineer"
    assert result["facts_created"] >= 3

    facts = list_facts(profile["id"], session=in_memory_db)
    contents = {f["content"] for f in facts}
    assert "Bob Engineer" in contents or "bob@example.com" in contents


def test_ingest_document_unsupported_raises(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    with pytest.raises(ValueError):
        ingest_document(profile["id"], b"not a real pdf", filename="resume.pdf", session=in_memory_db)