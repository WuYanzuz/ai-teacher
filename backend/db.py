"""Database initialization for the backend."""

from __future__ import annotations

from ai_teacher.storage.database import (
    Base,
    get_engine,
    migrate_dev_sqlite,
)


def init_backend_db() -> None:
    """Create all tables. Idempotent (create_all checkfirst)."""
    # Importing registers every table on the shared metadata.
    from ai_teacher.storage import models as _storage_models  # noqa: F401
    from . import models as _backend_models  # noqa: F401

    engine = get_engine()
    # Patch old local SQLite dev DBs before create_all (e.g. user -> app_user).
    migrate_dev_sqlite(engine)
    Base.metadata.create_all(engine)

    # Seed system quick-record templates once.
    from ai_teacher.storage.database import session_scope
    from .services.growth_templates import seed_default_templates
    with session_scope() as db:
        seed_default_templates(db)


def get_db():
    """Re-exported FastAPI session dependency."""
    from ai_teacher.storage.database import get_db as _get_db

    yield from _get_db()
