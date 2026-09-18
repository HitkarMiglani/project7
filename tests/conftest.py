"""
tests/conftest.py
Pytest fixtures and configuration for KnapResume testing.
Provides fast, isolated in-memory SQLite database sessions.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from src.database import Base


@pytest.fixture(scope="function")
def in_memory_db():
    """
    Creates a clean in-memory SQLite database engine for testing.
    """
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine, "connect")
    def _set_test_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

    # Import all models to ensure metadata is populated
    try:
        import src.models  # noqa: F401
    except ImportError:
        pass

    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
