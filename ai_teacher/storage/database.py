"""SQLAlchemy engine / session management (shared by ai_teacher and backend).

Dialect is chosen via config.yaml -> database.dialect:
  - sqlite:  local file (default for dev/test)
  - oracle:  python-oracledb thin mode (no Instant Client needed, 12.1+)

Models register on the same ``Base.metadata`` regardless of which file they
live in; create_all() creates every table imported so far.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..utils.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def database_url() -> str:
    """Build the SQLAlchemy URL from config.yaml + .env."""
    s = get_settings()
    db_cfg = s.yaml.get("database", {})
    dialect = db_cfg.get("dialect", "sqlite").lower()
    if dialect == "oracle":
        user = db_cfg.get("user", "AIWECHAT")
        password = os.getenv("ORACLE_PASSWORD", "")
        dsn = os.getenv("ORACLE_DSN", "").strip()
        if dsn:
            # EZ-connect style, e.g. host:1521/XEPDB1
            return f"oracle+oracledb://{user}:{password}@{dsn}"
        host = db_cfg.get("host", "127.0.0.1")
        port = db_cfg.get("port", 1521)
        service_name = db_cfg.get("service_name", "XEPDB1")
        return (
            f"oracle+oracledb://{user}:{password}@{host}:{port}"
            f"/?service_name={service_name}"
        )
    return f"sqlite:///{s.db_path.as_posix()}"


def get_engine() -> Engine:
    global _engine, SessionLocal
    if _engine is None:
        url = database_url()
        if url.startswith("sqlite"):
            Path(get_settings().db_path).parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                pool_pre_ping=True,
            )
        else:
            _engine = create_engine(
                url,
                pool_size=5,
                max_overflow=5,
                pool_recycle=300,
                pool_pre_ping=True,
            )
        SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transaction boundary for scripts and background tasks.

    Commits on clean exit, rolls back on exception, always closes.
    Do NOT hold this open across slow LLM calls — fetch, close, call AI,
    then open a new scope to write back.
    """
    get_engine()
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request.

    Read routes need no commit; write routes call ``db.commit()`` explicitly.
    FastAPI caches this generator per request, so ``current_user`` and the
    route handler share the same session.
    """
    get_engine()
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def migrate_dev_sqlite(engine: Engine) -> None:
    """Patch old local SQLite dev DBs up to the current schema.

    Oracle deployments always start from create_all(); this exists so devs
    keep their data after model changes:
      - rename the peewee-era ``user`` table to ``app_user`` (``user`` is an
        Oracle reserved word; fresh dev DBs use app_user from the start)
      - add the homework.child_name denormalized column
    """
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        names = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        if "user" in names and "app_user" not in names:
            conn.execute(text('ALTER TABLE "user" RENAME TO app_user'))
        if "homework" in names:
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(homework)"))}
            if "child_name" not in cols:
                conn.execute(
                    text("ALTER TABLE homework ADD COLUMN child_name VARCHAR(64)")
                )
