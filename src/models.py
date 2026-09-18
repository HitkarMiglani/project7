"""
src/models.py
SQLAlchemy ORM models for KnapResume:
- Profile: User profile container
- ProfileFact: Discrete verifiable facts (with float32 vector embedding storage)
- JD: Ingested and structured Job Descriptions
- JDRequirement: Extracted requirements/skills categorized by importance
- RunLog: Tailoring execution logs and section feedback
- Claim: Verifier output linking generated statements to cited facts with 3-state enum
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import numpy as np

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    LargeBinary,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship

from src.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Profile(Base):
    """
    User's persistent profile container.
    Stores high-level metadata, structured sections, and links to discrete facts.
    """
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, default="Default Profile")
    sections = Column(JSON, nullable=True)  # E.g. {"summary": "...", "target_role": "..."}
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    # Relationships
    facts = relationship(
        "ProfileFact",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="ProfileFact.id",
    )
    run_logs = relationship(
        "RunLog",
        back_populates="profile",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "sections": self.sections or {},
            "fact_count": len(self.facts) if self.facts else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None, # type: ignore
            "updated_at": self.updated_at.isoformat() if self.updated_at else None, # type: ignore
        }


class ProfileFact(Base):
    """
    A single discrete, verifiable fact from a user's resume/profile.
    Contains raw text, section classification, optional metadata flag, and vector embedding.
    """
    __tablename__ = "profile_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    section = Column(String(64), nullable=False, index=True)  # e.g., "experience", "education", "skills", "projects"
    content = Column(Text, nullable=False)
    is_mandatory = Column(Boolean, default=False, nullable=False)  # True for structural metadata (e.g. role title, dates)
    embedding = Column(LargeBinary, nullable=True)  # Stored as float32 binary buffer (ADR-006)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    # Relationships
    profile = relationship("Profile", back_populates="facts")
    cited_claims = relationship("Claim", back_populates="cited_fact")

    def set_embedding(self, vector: np.ndarray) -> None:
        """Serialize a 1D NumPy array of float32 to raw binary buffer."""
        if vector is None:
            self.embedding = None
            return
        arr = np.asarray(vector, dtype=np.float32)
        self.embedding = arr.tobytes()

    def get_embedding(self) -> Optional[np.ndarray]:
        """Deserialize raw binary buffer back into a float32 NumPy array."""
        if self.embedding is None:
            return None
        return np.frombuffer(self.embedding, dtype=np.float32)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "profile_id": self.profile_id,
            "section": self.section,
            "content": self.content,
            "is_mandatory": self.is_mandatory,
            "has_embedding": self.embedding is not None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class JD(Base):
    """
    Ingested Job Description with extracted structured data and role classification.
    """
    __tablename__ = "jds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_text = Column(Text, nullable=False)
    structured = Column(JSON, nullable=True)  # {"required_skills": [...], "nice_to_have": [...]}
    role_type = Column(String(64), nullable=True, index=True)  # e.g. "backend", "fullstack", "data", "ml"
    company = Column(String(255), nullable=True)
    job_title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    # Relationships
    requirements = relationship(
        "JDRequirement",
        back_populates="jd",
        cascade="all, delete-orphan",
        order_by="JDRequirement.id",
    )
    run_logs = relationship(
        "RunLog",
        back_populates="jd",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "company": self.company,
            "job_title": self.job_title,
            "role_type": self.role_type,
            "structured": self.structured or {},
            "requirements_count": len(self.requirements) if self.requirements else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class JDRequirement(Base):
    """
    Extracted requirement or skill from a Job Description.
    """
    __tablename__ = "jd_requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jd_id = Column(Integer, ForeignKey("jds.id", ondelete="CASCADE"), nullable=False, index=True)
    skill = Column(String(255), nullable=False)
    category = Column(String(32), default="required", nullable=False)  # "required" | "nice_to_have"
    importance = Column(Float, default=1.0, nullable=False)  # 0.0 to 1.0 weight
    embedding = Column(LargeBinary, nullable=True)

    # Relationships
    jd = relationship("JD", back_populates="requirements")

    def set_embedding(self, vector: np.ndarray) -> None:
        if vector is None:
            self.embedding = None
            return
        arr = np.asarray(vector, dtype=np.float32)
        self.embedding = arr.tobytes()

    def get_embedding(self) -> Optional[np.ndarray]:
        if self.embedding is None:
            return None
        return np.frombuffer(self.embedding, dtype=np.float32)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "jd_id": self.jd_id,
            "skill": self.skill,
            "category": self.category,
            "importance": self.importance,
            "has_embedding": self.embedding is not None,
        }


class RunLog(Base):
    """
    Records an execution run of the tailoring and verification engine.
    Stores runtime duration, output file paths, and weakest-section feedback.
    """
    __tablename__ = "run_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    jd_id = Column(Integer, ForeignKey("jds.id", ondelete="SET NULL"), nullable=True, index=True)
    feedback = Column(JSON, nullable=True)  # {"weakest_section": "...", "reasoning": "...", "matched_keywords": [...]}
    status = Column(String(32), default="pending", nullable=False)  # "pending", "running", "completed", "failed"
    duration_ms = Column(Integer, nullable=True)
    resume_pdf_path = Column(String(512), nullable=True)
    cover_pdf_path = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    # Relationships
    profile = relationship("Profile", back_populates="run_logs")
    jd = relationship("JD", back_populates="run_logs")
    claims = relationship(
        "Claim",
        back_populates="run_log",
        cascade="all, delete-orphan",
        order_by="Claim.id",
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "profile_id": self.profile_id,
            "jd_id": self.jd_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "feedback": self.feedback or {},
            "resume_pdf_path": self.resume_pdf_path,
            "cover_pdf_path": self.cover_pdf_path,
            "claims_count": len(self.claims) if self.claims else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Claim(Base):
    """
    Verification output for a discrete generated claim in the tailored resume.
    Tagged with one of: "verified", "inferred", "unsupported".
    """
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_log_id = Column(Integer, ForeignKey("run_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    state = Column(String(32), nullable=False, index=True)  # "verified", "inferred", "unsupported"
    score = Column(Float, nullable=True)  # Cosine similarity score or NLI entailment confidence
    cited_fact_id = Column(Integer, ForeignKey("profile_facts.id", ondelete="SET NULL"), nullable=True, index=True)

    # Relationships
    run_log = relationship("RunLog", back_populates="claims")
    cited_fact = relationship("ProfileFact", back_populates="cited_claims")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "run_log_id": self.run_log_id,
            "text": self.text,
            "state": self.state,
            "score": self.score,
            "cited_fact_id": self.cited_fact_id,
        }
