"""
tests/test_profile_service.py
Unit tests for the Profile & Fact CRUD service layer in src/profile_service.py:
creation/retrieval/update/delete, metadata tagging (is_mandatory inference),
vector embedding serialization, and error handling.
"""

import numpy as np
import pytest
from sqlalchemy.exc import IntegrityError

from src.profile_service import (
    ProfileNotFoundError,
    FactNotFoundError,
    add_fact,
    clear_fact_embedding,
    create_profile,
    delete_fact,
    delete_profile,
    get_fact,
    get_fact_embedding,
    get_profile,
    infer_is_mandatory,
    list_facts,
    list_profiles,
    update_fact,
    update_profile,
)


# ── Metadata tagging heuristics ─────────────────────────────────────────────

def test_infer_is_mandatory_structural_sections():
    assert infer_is_mandatory("contact", "alice@example.com") is True
    assert infer_is_mandatory("name", "Alice Developer") is True
    assert infer_is_mandatory("education", "B.S. Computer Science, MIT") is True
    assert infer_is_mandatory("certifications", "AWS Solutions Architect") is True


def test_infer_is_mandatory_matches_date_and_contact_patterns():
    assert infer_is_mandatory("experience", "2020 - Present") is True
    assert infer_is_mandatory("experience", "Jan 2021 - Mar 2023") is True
    assert infer_is_mandatory("experience", "+1 555-123-4567") is True
    assert infer_is_mandatory("experience", "https://github.com/alice") is True


def test_infer_is_mandatory_optional_achievement():
    assert infer_is_mandatory("experience", "Led a team of 5 engineers") is False
    assert infer_is_mandatory("projects", "Built ETL pipeline with Spark") is False
    assert infer_is_mandatory("skills", "Python, Docker, FastAPI") is False


# ── Profile CRUD ─────────────────────────────────────────────────────────────

def test_create_and_get_profile(in_memory_db):
    created = create_profile(name="Alice Developer", sections={"summary": "Backend engineer"}, session=in_memory_db)
    assert created["id"] is not None
    assert created["name"] == "Alice Developer"
    assert created["sections"]["summary"] == "Backend engineer"
    assert created["fact_count"] == 0

    fetched = get_profile(created["id"], session=in_memory_db)
    assert fetched["id"] == created["id"]
    assert fetched["name"] == created["name"]


def test_create_profile_rejects_empty_name(in_memory_db):
    with pytest.raises(ValueError):
        create_profile(name="   ", session=in_memory_db)


def test_list_profiles(in_memory_db):
    assert list_profiles(session=in_memory_db) == []
    p1 = create_profile(name="Alice", session=in_memory_db)
    p2 = create_profile(name="Bob", session=in_memory_db)
    names = [p["name"] for p in list_profiles(session=in_memory_db)]
    assert names == ["Alice", "Bob"]
    assert [p["id"] for p in list_profiles(session=in_memory_db)] == [p1["id"], p2["id"]]


def test_update_profile(in_memory_db):
    created = create_profile(name="Alice", session=in_memory_db)
    updated = update_profile(
        created["id"],
        name="Alice Developer",
        sections={"target_role": "Staff Engineer"},
        session=in_memory_db,
    )
    assert updated["name"] == "Alice Developer"
    assert updated["sections"]["target_role"] == "Staff Engineer"


def test_delete_profile(in_memory_db):
    created = create_profile(name="Alice", session=in_memory_db)
    delete_profile(created["id"], session=in_memory_db)
    with pytest.raises(ProfileNotFoundError):
        get_profile(created["id"], session=in_memory_db)


def test_get_missing_profile_raises(in_memory_db):
    with pytest.raises(ProfileNotFoundError):
        get_profile(99999, session=in_memory_db)


# ── Fact CRUD ────────────────────────────────────────────────────────────────

def test_add_and_get_fact(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    fact = add_fact(profile["id"], "skills", "Python, SQL, Docker", session=in_memory_db)
    assert fact["id"] is not None
    assert fact["profile_id"] == profile["id"]
    assert fact["section"] == "skills"
    assert fact["content"] == "Python, SQL, Docker"
    assert fact["has_embedding"] is False

    fetched = get_fact(fact["id"], session=in_memory_db)
    assert fetched["content"] == fact["content"]


def test_add_fact_infers_mandatory_from_section(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    education = add_fact(profile["id"], "education", "MIT B.S. CS", session=in_memory_db)
    achievement = add_fact(profile["id"], "experience", "Scaled service to 1M users", session=in_memory_db)
    assert education["is_mandatory"] is True
    assert achievement["is_mandatory"] is False


def test_add_fact_explicit_mandatory_override(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    fact = add_fact(
        profile["id"], "experience", "Chief Architect", is_mandatory=True, session=in_memory_db
    )
    assert fact["is_mandatory"] is True


def test_add_fact_validates_input(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    with pytest.raises(ValueError):
        add_fact(profile["id"], "", "content", session=in_memory_db)
    with pytest.raises(ValueError):
        add_fact(profile["id"], "skills", "", session=in_memory_db)


def test_add_fact_to_missing_profile_raises(in_memory_db):
    with pytest.raises(ProfileNotFoundError):
        add_fact(99999, "skills", "Python", session=in_memory_db)


def test_list_facts_with_and_without_section_filter(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    add_fact(profile["id"], "skills", "Python", session=in_memory_db)
    add_fact(profile["id"], "skills", "Docker", session=in_memory_db)
    add_fact(profile["id"], "education", "MIT B.S. CS", session=in_memory_db)

    all_facts = list_facts(profile["id"], session=in_memory_db)
    assert len(all_facts) == 3

    skills = list_facts(profile["id"], section="skills", session=in_memory_db)
    assert len(skills) == 2
    assert all(f["section"] == "skills" for f in skills)


def test_update_fact(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    fact = add_fact(profile["id"], "skills", "Python", session=in_memory_db)
    updated = update_fact(
        fact["id"], content="Python, FastAPI", is_mandatory=True, session=in_memory_db
    )
    assert updated["content"] == "Python, FastAPI"
    assert updated["is_mandatory"] is True


def test_update_fact_rejects_empty_content(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    fact = add_fact(profile["id"], "skills", "Python", session=in_memory_db)
    with pytest.raises(ValueError):
        update_fact(fact["id"], content=" ", session=in_memory_db)


def test_delete_fact(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    fact = add_fact(profile["id"], "skills", "Python", session=in_memory_db)
    delete_fact(fact["id"], session=in_memory_db)
    with pytest.raises(FactNotFoundError):
        get_fact(fact["id"], session=in_memory_db)


def test_get_missing_fact_raises(in_memory_db):
    with pytest.raises(FactNotFoundError):
        get_fact(99999, session=in_memory_db)


# ── Embedding serialization ──────────────────────────────────────────────────

def test_fact_embedding_round_trip(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    vector = np.random.randn(384).astype(np.float32)
    fact = add_fact(
        profile["id"], "experience",
        "Built a distributed system in Python",
        embedding=vector,
        session=in_memory_db,
    )
    assert fact["has_embedding"] is True

    fetched = get_fact(fact["id"], session=in_memory_db)
    assert fetched["has_embedding"] is True

    deserialized = get_fact_embedding(fact["id"], session=in_memory_db)
    assert deserialized is not None
    assert deserialized.shape == (384,)
    assert deserialized.dtype == np.float32
    assert np.allclose(deserialized, vector, atol=1e-6)


def test_fact_without_embedding_returns_none(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    fact = add_fact(profile["id"], "skills", "Python", session=in_memory_db)
    assert fact["has_embedding"] is False
    assert get_fact_embedding(fact["id"], session=in_memory_db) is None


def test_clear_fact_embedding(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    vector = np.random.randn(128).astype(np.float32)
    fact = add_fact(profile["id"], "experience", "Scaled systems", embedding=vector, session=in_memory_db)
    assert get_fact_embedding(fact["id"], session=in_memory_db) is not None

    cleared = clear_fact_embedding(fact["id"], session=in_memory_db)
    assert cleared["has_embedding"] is False
    assert get_fact_embedding(fact["id"], session=in_memory_db) is None


# ── Cascade integrity ────────────────────────────────────────────────────────

def test_delete_profile_cascades_facts(in_memory_db):
    profile = create_profile(name="Alice", session=in_memory_db)
    add_fact(profile["id"], "skills", "Python", session=in_memory_db)
    add_fact(profile["id"], "experience", "Led team", session=in_memory_db)

    delete_profile(profile["id"], session=in_memory_db)

    with pytest.raises(ProfileNotFoundError):
        get_profile(profile["id"], session=in_memory_db)
    from src.models import ProfileFact
    assert in_memory_db.query(ProfileFact).count() == 0