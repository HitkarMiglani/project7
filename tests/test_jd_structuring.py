"""
tests/test_jd_structuring.py
Stage 2.1 — JD text cleaning & boilerplate filtering.
Stage 2.2 — KeyBERT keyword extraction + required/nice_to_have split.
Stage 2.3 — Role-type classification + JD/JDRequirement persistence.

2.1 covers EEO/legal/promo stripping, company + job-title extraction,
section grouping (incl. nice-to-have aliases), the structure_jd
orchestrator, and empty-input validation. 2.2/2.3 cover keyword
discovery, cue-based splitting, role classification, and DB persistence.
"""

import pytest

from src.jd_structuring import (
    classify_role_type,
    clean_jd_text,
    extract_company,
    extract_job_title,
    extract_keywords,
    extract_requirements,
    extract_sections,
    persist_jd,
    structure_jd,
)


SAMPLE_JD = """\
Senior Backend Engineer at Acme Corp

About Us
Acme Corp builds payments infrastructure for marketplaces.

Responsibilities:
- Design and ship Python microservices on AWS
- Own Postgres schema changes and query performance

Requirements:
- 5+ years building backend systems in Python
- Hands-on with Postgres, Docker, and Kafka

Nice to Have:
- Experience with Spark and Terraform

Benefits:
We offer free lunch, ping-pong, and nap pods in the office.

We are an equal opportunity employer. All qualified applicants will receive
consideration without regard to race, color, religion, sex, or disability.
"""


# ── clean_jd_text ────────────────────────────────────────────────────────────

def test_clean_strips_eeo_and_promo_keeps_requirements():
    cleaned = clean_jd_text(SAMPLE_JD)
    assert "equal opportunity employer" not in cleaned.lower()
    assert "ping-pong" not in cleaned.lower()
    assert "Python microservices" in cleaned
    assert "Postgres, Docker, and Kafka" in cleaned


def test_clean_is_idempotent():
    once = clean_jd_text(SAMPLE_JD)
    assert clean_jd_text(once) == once


def test_clean_empty_and_boilerplate_only_raise():
    with pytest.raises(ValueError):
        clean_jd_text("   ")
    with pytest.raises(ValueError):
        clean_jd_text("We are an equal opportunity employer.")


# ── extract_company / extract_job_title ──────────────────────────────────────

def test_extract_company_inline_at_pattern():
    assert extract_company(SAMPLE_JD) == "Acme Corp"


def test_extract_company_explicit_label():
    assert extract_company("Company: Globex Inc\nBackend role") == "Globex Inc"


def test_extract_company_unknown_returns_empty():
    assert extract_company("Backend Engineer\nBuild things with Python.") == ""


def test_extract_job_title_first_line():
    assert extract_job_title(SAMPLE_JD) == "Senior Backend Engineer at Acme Corp"


def test_extract_job_title_explicit_label():
    text = "Company: Globex\nJob Title: Data Engineer\nBuild pipelines."
    assert extract_job_title(text) == "Data Engineer"


def test_extract_job_title_empty_returns_empty():
    assert extract_job_title("   ") == ""


# ── extract_sections ─────────────────────────────────────────────────────────

def test_extract_sections_canonical_keys():
    sections = extract_sections(SAMPLE_JD)
    assert "requirements" in sections
    assert "responsibilities" in sections
    assert "nice_to_have" in sections
    assert "benefits" in sections
    assert any("Python" in line for line in sections["requirements"])


def test_extract_sections_alias_mapping():
    text = "Backend Role\n\nMust Have:\n- Python\n\nBonus Points:\n- Rust"
    sections = extract_sections(text)
    assert "requirements" in sections
    assert "nice_to_have" in sections


def test_extract_sections_pre_header_body_is_other():
    sections = extract_sections("Senior Backend Engineer\nBuild things.")
    assert "other" in sections


def test_extract_sections_empty_raises():
    with pytest.raises(ValueError):
        extract_sections("  ")


# ── structure_jd ─────────────────────────────────────────────────────────────

def test_structure_jd_end_to_end():
    result = structure_jd(SAMPLE_JD)
    assert result["company"] == "Acme Corp"
    assert "Senior Backend Engineer" in result["job_title"]
    assert "equal opportunity" not in result["cleaned_text"].lower()
    assert "Python" in result["cleaned_text"]
    assert set(result["sections"].keys()) >= {"requirements", "responsibilities"}


def test_structure_jd_no_headers_falls_back_to_cleaned_raw():
    text = "Backend Engineer at Initech\nBuild Python APIs.\nWe offer free lunch daily."
    result = structure_jd(text)
    assert "Python APIs" in result["cleaned_text"]
    assert "free lunch" not in result["cleaned_text"].lower()


def test_structure_jd_empty_raises():
    with pytest.raises(ValueError):
        structure_jd("   ")


# ── Stage 2.2: extract_keywords ──────────────────────────────────────────────

def test_extract_keywords_returns_scored_phrases():
    pairs = extract_keywords("Python backend engineer with Postgres Docker Kafka experience",
                             top_n=5)
    assert len(pairs) == 5
    assert all(isinstance(p, str) and p for p, _ in pairs)
    assert all(isinstance(s, float) for _, s in pairs)
    assert pairs == sorted(pairs, key=lambda kv: -kv[1])


def test_extract_keywords_empty_raises():
    with pytest.raises(ValueError):
        extract_keywords("   ")


# ── Stage 2.2: extract_requirements ──────────────────────────────────────────

def test_extract_requirements_splits_required_vs_nice():
    reqs = extract_requirements(SAMPLE_JD)
    required = {r["skill"] for r in reqs["required_skills"]}
    nice = {r["skill"] for r in reqs["nice_to_have"]}
    assert {"Python", "Postgres", "Docker", "Kafka"} <= required
    assert {"Spark", "Terraform"} <= nice
    assert not (required & nice)
    assert all(0.0 <= r["importance"] <= 1.0
               for r in reqs["required_skills"] + reqs["nice_to_have"])


def test_extract_requirements_cue_words_mark_nice():
    text = ("Requirements:\n- 5 years Python backend development\n"
            "- Familiarity with Rust is a plus")
    reqs = extract_requirements(text)
    required = {r["skill"] for r in reqs["required_skills"]}
    nice = {r["skill"] for r in reqs["nice_to_have"]}
    assert "Python" in required
    assert "Rust" in nice


def test_extract_requirements_empty_raises():
    with pytest.raises(ValueError):
        extract_requirements("  ")


# ── Stage 2.3: classify_role_type ────────────────────────────────────────────

def test_classify_backend_data_frontend():
    backend_jd = "Backend Engineer\nBuild Python microservices with Postgres and Docker."
    data_jd = "Data Engineer\nBuild ETL pipelines with Spark Airflow and Snowflake."
    frontend_jd = "Frontend Engineer\nBuild React interfaces with TypeScript and CSS."
    assert classify_role_type(backend_jd, "Backend Engineer") == "backend"
    assert classify_role_type(data_jd, "Data Engineer") == "data"
    assert classify_role_type(frontend_jd, "Frontend Engineer") == "frontend"


def test_classify_title_override_without_model():
    assert classify_role_type("Build things.", "Mobile Engineer") == "mobile"
    assert classify_role_type("Build things.", "DevOps Engineer") == "devops"


def test_classify_embedding_path_no_title():
    # No title cue: exercises the embedding cosine branch.
    text = ("We need someone to design Python microservices, own Postgres "
            "schemas, and ship Docker containers to AWS.")
    assert classify_role_type(text) in {
        "backend", "frontend", "fullstack", "data", "devops", "mobile", "ml"}


def test_classify_empty_raises():
    with pytest.raises(ValueError):
        classify_role_type("   ")


# ── Stage 2.3: persist_jd ────────────────────────────────────────────────────

def test_persist_jd_creates_rows_with_embeddings(in_memory_db):
    from src.models import JD, JDRequirement

    result = persist_jd(SAMPLE_JD, session=in_memory_db)
    assert result["company"] == "Acme Corp"
    assert result["role_type"] == "backend"
    assert "Python" in result["required_skills"]
    assert "Spark" in result["nice_to_have"]
    assert result["requirements_count"] > 0

    jd = in_memory_db.query(JD).filter(JD.id == result["id"]).one()
    assert jd.structured["required_skills"] == result["required_skills"]
    assert jd.structured["nice_to_have"] == result["nice_to_have"]

    rows = in_memory_db.query(JDRequirement).filter(
        JDRequirement.jd_id == result["id"]).all()
    assert len(rows) == result["requirements_count"]
    assert all(r.get_embedding() is not None for r in rows)
    assert {r.category for r in rows} >= {"required", "nice_to_have"}


def test_persist_jd_empty_raises(in_memory_db):
    with pytest.raises(ValueError):
        persist_jd("   ", session=in_memory_db)
