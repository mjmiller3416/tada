"""Shared fixtures for the decay-engine test suite (Phase 7).

The pure scheduling functions need no database — `make_task` builds plain
Task objects with every field set explicitly (SQLAlchemy column defaults
only apply on INSERT, so a detached Task would otherwise carry Nones).
The query-backed functions run against a fresh in-memory SQLite database
per test; scheduling._aware() already normalizes SQLite's naive UTC
datetimes, so the models are compatible as-is.
"""

import os

# Must be set before any `app.` import — app.config reads the environment
# at import time, and app.database builds the (never-connected) engine.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Setting, Task, User


@pytest.fixture()
def db():
    """A fresh in-memory SQLite session with all tables created."""
    engine = create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def make_task():
    """Factory for plain Task objects (usable with or without a session)."""

    def _make(**overrides) -> Task:
        fields = dict(
            name="Wipe counters",
            room_id=None,
            category="cleaning",  # deprecated column; kept explicit for detached objects
            task_type="routine",
            cadence_days=7,
            estimated_minutes=10,
            effort="quick",
            guest_facing=False,
            preferred_day=None,
            last_done_at=None,
            snoozed_until=None,
            assignee_id=None,
            claimable=False,
            is_active=True,
        )
        fields.update(overrides)
        return Task(**fields)

    return _make


@pytest.fixture()
def owner(db):
    """The owner, pinned to UTC so streak-day math in tests is exact."""
    user = User(name="Maryann", password_hash="x", role="owner")
    db.add(user)
    db.flush()
    db.add(Setting(user_id=user.id, key="timezone", value="UTC"))
    db.flush()
    return user


@pytest.fixture()
def kid(db):
    user = User(name="Sam", password_hash="x", role="kid")
    db.add(user)
    db.flush()
    return user
