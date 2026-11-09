"""DB initialization and helper queries.

Function signatures are unchanged from the peewee era so the legacy
wcferry bot (dispatcher.py) keeps working; the internals are SQLAlchemy 2.x.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update

from .database import Base, get_engine, migrate_dev_sqlite, session_scope
from .models import ALL_TABLES, Child, GrowthMetric, Homework


def init_db() -> None:
    """Bind the engine and create storage tables. Legacy bot entry point."""
    from . import models  # noqa: F401  (register metadata)

    engine = get_engine()
    migrate_dev_sqlite(engine)
    Base.metadata.create_all(engine, tables=[t.__table__ for t in ALL_TABLES])


def close_db() -> None:
    return None


def upsert_child(name: str, parent_wxid: str | None = None, group_nick: str | None = None) -> Child:
    """Find-or-create a child, keyed by (parent_wxid, name) when possible."""
    with session_scope() as db:
        stmt = select(Child).where(Child.name == name)
        if parent_wxid:
            stmt = stmt.where(Child.parent_wxid == parent_wxid)
        existing = db.scalars(stmt).first()
        now = datetime.now()
        if existing:
            existing.last_seen = now
            if group_nick and not existing.group_nick_pattern:
                existing.group_nick_pattern = group_nick
            db.commit()
            db.refresh(existing)
            return existing
        child = Child(
            name=name,
            parent_wxid=parent_wxid or None,
            group_nick_pattern=group_nick,
            first_seen=now,
            last_seen=now,
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        return child


def record_homework(
    *,
    child: Child,
    group_roomid: str,
    msg_id: int,
    media_type: str,
    media_path: str | None = None,
    transcript: str | None = None,
    is_homework: bool = True,
    feedback: str | None = None,
) -> Homework | None:
    """Insert a homework row. Returns None if duplicate (group_roomid, msg_id)."""
    with session_scope() as db:
        exists = db.scalar(
            select(Homework.id).where(
                Homework.group_roomid == group_roomid,
                Homework.msg_id == msg_id,
            )
        )
        if exists:
            return None
        hw = Homework(
            child_id=child.id,
            group_roomid=group_roomid,
            msg_id=msg_id,
            media_type=media_type,
            media_path=media_path,
            raw_transcript=transcript,
            is_homework=1 if is_homework else 0,
            feedback=feedback,
        )
        db.add(hw)
        db.commit()
        db.refresh(hw)
        return hw


def add_metric(child: Child, homework: Homework, dimension: str, score: float, note: str | None = None) -> GrowthMetric:
    with session_scope() as db:
        metric = GrowthMetric(
            child_id=child.id,
            homework_id=homework.id,
            dimension=dimension,
            score=score,
            note=note,
        )
        db.add(metric)
        db.commit()
        db.refresh(metric)
        return metric


def child_history(child: Child, limit: int = 20) -> list[dict]:
    with session_scope() as db:
        rows = db.scalars(
            select(Homework)
            .where(Homework.child_id == child.id, Homework.is_homework == 1)
            .order_by(Homework.created_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "id": h.id,
                "date": h.created_at.strftime("%Y-%m-%d") if h.created_at else "?",
                "type": h.media_type,
                "feedback": h.feedback or "",
                "metric": None,  # filled in by growth report if needed
            }
            for h in rows
        ]


def cleanup_old_cache(cache_dir, retention_days: int) -> int:
    """Delete cached media files older than retention_days. Returns count."""
    cache_dir = Path(cache_dir)
    if not cache_dir.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    count = 0
    for p in cache_dir.rglob("*"):
        if not p.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                p.unlink()
                count += 1
            except OSError:
                pass
    with session_scope() as db:
        db.execute(
            update(Homework)
            .where(Homework.created_at < cutoff, Homework.media_path.is_not(None))
            .values(media_path=None)
        )
    return count
