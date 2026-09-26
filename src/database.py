"""
src/database.py
Database connection, engine configuration, and session management for KnapResume.
Enforces SQLite WAL (Write-Ahead Logging) mode and busy timeout for thread safety.
"""

import os
from pathlib import Path
from typing import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from src.logger import get_logger

logger = get_logger("database")

# Project root directory and default database path
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "knapresume.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# SQLAlchemy engine with check_same_thread=False for multi-threaded Flask support
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Configure SQLite connection pragmas:
    - WAL mode allows concurrent readers alongside a writer.
    - busy_timeout=5000 prevents 'database is locked' errors under fast re-runs.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative Base for models
Base = declarative_base()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    logger.debug("DB session opened")
    try:
        yield session
        session.commit()
        logger.debug("DB session committed")
    except Exception:
        session.rollback()
        logger.exception("DB session rolled back")
        raise
    finally:
        session.close()
        logger.debug("DB session closed")


def init_db():
    """Create all registered database tables if they do not already exist."""
    import src.models  # Ensure all models are imported before creating tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized at %s", DB_PATH)
