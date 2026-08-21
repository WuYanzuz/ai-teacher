"""Database initialization and helpers for the backend."""

from __future__ import annotations

from ai_teacher.storage.db import init_db
from ai_teacher.storage.models import ALL_TABLES

from .models import ALL_NEW_TABLES, _patch_homework


def init_backend_db() -> None:
    """Create all tables (existing + new). Idempotent."""
    init_db()  # existing tables
    _patch_homework()
    # peewee: add columns to existing tables that don't have them
    from ai_teacher.storage.models import Homework, db
    for col in ("submit_user", "classroom"):
        try:
            db.execute_sql(f"ALTER TABLE homework ADD COLUMN {col}_id INTEGER")
        except Exception:
            pass  # column already exists
    # Create new tables
    db.create_tables(ALL_NEW_TABLES, safe=True)


def get_db():
    """FastAPI dependency: yield a peewee connection."""
    from ai_teacher.storage.models import db
    if db.is_closed():
        db.connect(reuse_if_open=True)
    try:
        yield db
    finally:
        pass  # keep connection open (sqlite is fast)
