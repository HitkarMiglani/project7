"""
tests/test_models.py
Unit tests for SQLAlchemy models, constraints, relationships, cascades,
and binary vector embedding serialization.
"""

import pytest
import numpy as np
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from src.models import (
    Profile,
    ProfileFact,
    JD,
    JDRequirement,
    RunLog,
    Claim,
)


def test_profile_creation_and_dict(in_memory_db):
    """Test creating a Profile with JSON sections and converting to dict."""
    session = in_memory_db
    profile = Profile(
        name="Alice Developer",
        sections={"summary": "Experienced backend engineer", "target_role": "Backend Engineer"},
    )
    session.add(profile)
    session.commit()

    assert profile.id is not None
    assert profile.name == "Alice Developer"
    assert profile.sections["summary"] == "Experienced backend engineer"
    assert isinstance(profile.created_at, datetime)

    data = profile.to_dict()
    assert data["id"] == profile.id
    assert data["name"] == "Alice Developer"
    assert data["sections"]["target_role"] == "Backend Engineer"
    assert data["fact_count"] == 0


def test_profile_fact_with_binary_embedding(in_memory_db):
    """Test creating a ProfileFact, storing float32 embeddings, and deserializing."""
    session = in_memory_db
    profile = Profile(name="Bob")
    session.add(profile)
    session.commit()

    fact = ProfileFact(
        profile_id=profile.id,
        section="experience",
        content="Engineered high-throughput event processing pipeline in Python using asyncio.",
        is_mandatory=False,
    )
    
    # 384-dimensional vector
    sample_vector = np.random.randn(384).astype(np.float32)
    fact.set_embedding(sample_vector)

    session.add(fact)
    session.commit()

    retrieved_fact = session.query(ProfileFact).filter_by(id=fact.id).first()
    assert retrieved_fact is not None
    assert retrieved_fact.section == "experience"
    assert retrieved_fact.is_mandatory is False
    assert retrieved_fact.embedding is not None

    # Verify deserialization
    retrieved_vector = retrieved_fact.get_embedding()
    assert retrieved_vector is not None
    assert retrieved_vector.shape == (384,)
    assert retrieved_vector.dtype == np.float32
    assert np.allclose(retrieved_vector, sample_vector, atol=1e-6)

    fact_dict = retrieved_fact.to_dict()
    assert fact_dict["has_embedding"] is True
    assert fact_dict["content"] == fact.content


def test_profile_fact_cascade_deletion(in_memory_db):
    """Test that deleting a profile automatically deletes all associated facts."""
    session = in_memory_db
    profile = Profile(name="Charlie")
    session.add(profile)
    session.commit()

    fact1 = ProfileFact(profile_id=profile.id, section="skills", content="Python, SQL")
    fact2 = ProfileFact(profile_id=profile.id, section="education", content="B.S. Computer Science")
    session.add_all([fact1, fact2])
    session.commit()

    assert session.query(ProfileFact).filter_by(profile_id=profile.id).count() == 2

    # Delete profile
    session.delete(profile)
    session.commit()

    assert session.query(ProfileFact).filter_by(profile_id=profile.id).count() == 0


def test_foreign_key_enforcement(in_memory_db):
    """Test that SQLite foreign key pragma rejects orphan child records."""
    session = in_memory_db
    orphan_fact = ProfileFact(
        profile_id=99999,  # Non-existent profile
        section="experience",
        content="Invalid fact",
    )
    session.add(orphan_fact)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_jd_and_requirements(in_memory_db):
    """Test JD ingestion, structured requirements categorization, and embeddings."""
    session = in_memory_db
    jd = JD(
        raw_text="We are hiring a Senior Python Engineer with Docker and FastAPI experience.",
        company="TechCorp",
        job_title="Senior Python Engineer",
        role_type="backend",
        structured={"required_skills": ["Python", "Docker"], "nice_to_have": ["FastAPI"]},
    )
    session.add(jd)
    session.commit()

    req1 = JDRequirement(jd_id=jd.id, skill="Python", category="required", importance=1.0)
    req2 = JDRequirement(jd_id=jd.id, skill="FastAPI", category="nice_to_have", importance=0.6)
    
    vec = np.ones(384, dtype=np.float32)
    req1.set_embedding(vec)

    session.add_all([req1, req2])
    session.commit()

    assert len(jd.requirements) == 2
    assert jd.to_dict()["requirements_count"] == 2
    assert req1.get_embedding() is not None
    assert req2.get_embedding() is None

    # Cascade delete test
    session.delete(jd)
    session.commit()
    assert session.query(JDRequirement).filter_by(jd_id=jd.id).count() == 0


def test_run_log_and_claims_verification(in_memory_db):
    """Test RunLog recording feedback and Claim verification 3-state output."""
    session = in_memory_db
    profile = Profile(name="Dana")
    jd = JD(raw_text="Data Engineer role", company="DataCo")
    session.add_all([profile, jd])
    session.commit()

    fact = ProfileFact(profile_id=profile.id, section="projects", content="Built ETL with Spark")
    session.add(fact)
    session.commit()

    run = RunLog(
        profile_id=profile.id,
        jd_id=jd.id,
        status="completed",
        duration_ms=4500,
        feedback={"weakest_section": "experience", "matched_keywords": ["Spark"]},
        resume_pdf_path="outputs/dana_resume.pdf",
    )
    session.add(run)
    session.commit()

    claim_verified = Claim(
        run_log_id=run.id,
        text="Architected distributed ETL pipelines leveraging Apache Spark.",
        state="verified",
        score=0.92,
        cited_fact_id=fact.id,
    )
    claim_inferred = Claim(
        run_log_id=run.id,
        text="Collaborated with cross-functional data teams.",
        state="inferred",
        score=0.74,
    )
    claim_unsupported = Claim(
        run_log_id=run.id,
        text="Led 50-person engineering department as VP.",
        state="unsupported",
        score=0.15,
    )

    session.add_all([claim_verified, claim_inferred, claim_unsupported])
    session.commit()

    assert len(run.claims) == 3
    claims_states = [c.state for c in run.claims]
    assert "verified" in claims_states
    assert "inferred" in claims_states
    assert "unsupported" in claims_states
    assert claim_verified.cited_fact.content == "Built ETL with Spark"
