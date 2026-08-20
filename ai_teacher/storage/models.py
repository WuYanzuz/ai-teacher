"""Peewee ORM models."""

from __future__ import annotations

from datetime import datetime

from peewee import (
    AutoField,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

from ..utils.config import get_settings

db = SqliteDatabase(None)  # bound in db.init_db()


class _Base(Model):
    class Meta:
        database = db


class Child(_Base):
    """A child tracked in the system.

    The teacher may register a child explicitly (preferred) or we infer one
    from group nicknames.
    """

    id = AutoField()
    name = CharField(index=True)  # teacher-given name (preferred)
    parent_wxid = CharField(index=True)  # nullable: a child may have two parents
    group_nick_pattern = CharField(null=True)  # e.g. "X爸", "X妈妈"
    first_seen = DateTimeField(default=datetime.now)
    last_seen = DateTimeField(default=datetime.now)
    notes = TextField(null=True)

    class Meta:
        database = db


class Homework(_Base):
    """A single piece of homework submitted by a parent."""

    id = AutoField()
    child = ForeignKeyField(Child, backref="homeworks", on_delete="CASCADE")
    group_roomid = CharField(index=True)
    msg_id = IntegerField(index=True)  # wcferry msg id, for de-dup
    media_type = CharField()  # image / voice / video
    media_path = CharField(null=True)  # local file path; cleaned up after retention
    raw_transcript = TextField(null=True)  # ASR output for voice/video
    is_homework = IntegerField()  # 0/1 — classifier result
    feedback = TextField(null=True)  # AI feedback
    teacher_review = TextField(null=True)  # teacher may add notes later
    created_at = DateTimeField(default=datetime.now, index=True)

    class Meta:
        database = db
        indexes = (
            (("group_roomid", "msg_id"), True),  # unique
        )


class GrowthMetric(_Base):
    """Per-homework metric for growth tracking."""

    id = AutoField()
    child = ForeignKeyField(Child, backref="metrics", on_delete="CASCADE")
    homework = ForeignKeyField(Homework, backref="metrics", on_delete="CASCADE")
    dimension = CharField()  # e.g. 专注度 / 表达力 / 准确度
    score = FloatField()  # 0-5
    note = TextField(null=True)
    created_at = DateTimeField(default=datetime.now)


ALL_TABLES = [Child, Homework, GrowthMetric]
