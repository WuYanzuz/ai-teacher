"""DB initialization and helper queries."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .models import ALL_TABLES, Child, GrowthMetric, Homework, db


def init_db() -> None:
    """Bind SQLite path and create tables."""
    from ..utils.config import get_settings

    settings = get_settings()
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db.init(str(path))
    db.connect(reuse_if_open=True)
    db.create_tables(ALL_TABLES, safe=True)


def close_db() -> None:
    if not db.is_closed():
        db.close()


def upsert_child(name: str, parent_wxid: str | None = None, group_nick: str | None = None) -> Child:
    """Find-or-create a child, keyed by (parent_wxid, name) when possible."""
    qs = Child.select().where(Child.name == name)
    if parent_wxid:
        qs = qs.where(Child.parent_wxid == parent_wxid)
    existing = qs.first()
    now = datetime.now()
    if existing:
        existing.last_seen = now
        if group_nick and not existing.group_nick_pattern:
            existing.group_nick_pattern = group_nick
        existing.save()
        return existing
    return Child.create(
        name=name,
        parent_wxid=parent_wxid,
        group_nick_pattern=group_nick,
        first_seen=now,
        last_seen=now,
    )


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
    """Insert a homework row. Returns None if duplicate (msg_id)."""
    if Homework.select().where(
        (Homework.group_roomid == group_roomid) & (Homework.msg_id == msg_id)
    ).exists():
        return None
    return Homework.create(
        child=child,
        group_roomid=group_roomid,
        msg_id=msg_id,
        media_type=media_type,
        media_path=media_path,
        raw_transcript=transcript,
        is_homework=1 if is_homework else 0,
        feedback=feedback,
    )


def add_metric(child: Child, homework: Homework, dimension: str, score: float, note: str | None = None) -> GrowthMetric:
    return GrowthMetric.create(
        child=child,
        homework=homework,
        dimension=dimension,
        score=score,
        note=note,
    )


def child_history(child: Child, limit: int = 20) -> list[dict]:
    rows = (
        Homework.select()
        .where(Homework.child == child, Homework.is_homework == 1)
        .order_by(Homework.created_at.desc())
        .limit(limit)
    )
    out: list[dict] = []
    for h in rows:
        out.append(
            {
                "date": h.created_at.strftime("%Y-%m-%d"),
                "type": h.media_type,
                "feedback": h.feedback or "",
                "metric": None,  # filled in by growth report if needed
            }
        )
    return out


def cleanup_old_cache(cache_dir, retention_days: int) -> int:
    """Delete cached media files older than retention_days. Returns count."""
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
    # Also clear stale media_path in DB rows
    Homework.update(media_path=None).where(
        Homework.created_at < cutoff, Homework.media_path.is_null(False)
    ).execute()
    return count
