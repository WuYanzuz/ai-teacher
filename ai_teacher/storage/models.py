"""SQLAlchemy ORM models for the legacy core tables.

Tables (names kept stable for the SQLite -> Oracle migration):
  - Child        -> ``child``
  - Homework     -> ``homework``
  - GrowthMetric -> ``growthmetric`` (historical peewee table name)

The backend-specific tables (app_user / classroom / membership / auth_token
plus growth-checkin and report tables) live in ``backend/models.py``; both
modules share the same ``Base.metadata`` from ``.database``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Child(Base):
    """A child tracked in the system.

    New class-scoped features (checkin/reports) key off
    ``(classroom_id, child_name)`` directly rather than this global table,
    because children in different classes may share a name.
    """

    __tablename__ = "child"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # nullable: Oracle treats '' as NULL. Migrations normalize "" -> None.
    parent_wxid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    group_nick_pattern: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)
    last_seen: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    homeworks: Mapped[list["Homework"]] = relationship(
        back_populates="child", cascade="all, delete-orphan"
    )


class Homework(Base):
    """A single piece of homework submitted by a parent."""

    __tablename__ = "homework"
    __table_args__ = (
        UniqueConstraint("group_roomid", "msg_id", name="uq_homework_room_msg"),
        Index("ix_homework_class_created", "classroom_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    child_id: Mapped[int] = mapped_column(
        ForeignKey("child.id", ondelete="CASCADE"), nullable=False
    )
    group_roomid: Mapped[str] = mapped_column(String(64), nullable=False)
    msg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # synthetic ms timestamp
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    media_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    raw_transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_homework: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 0/1
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    teacher_review: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.now, index=True
    )
    # Plain integer columns (no DB-level FK): keeps the legacy ai_teacher
    # storage layer independent of the backend tables. Relationships are wired
    # up in backend/models.py with explicit join conditions.
    submit_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    classroom_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Denormalized child name scoped to the class; backfilled on migration and
    # written directly by the upload route going forward.
    child_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    child: Mapped[Child] = relationship(back_populates="homeworks")
    # submit_user / classroom relationships are attached in backend/models.py


class GrowthMetric(Base):
    """Per-homework metric for growth tracking."""

    __tablename__ = "growthmetric"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    child_id: Mapped[int] = mapped_column(
        ForeignKey("child.id", ondelete="CASCADE"), nullable=False
    )
    homework_id: Mapped[int] = mapped_column(
        ForeignKey("homework.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 0-5
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)


ALL_TABLES = [Child, Homework, GrowthMetric]
