"""SQLAlchemy models for the backend.

Auth / class tables:
  - User        -> ``app_user``  (``user`` is an Oracle reserved word)
  - Classroom
  - Membership
  - AuthToken

Growth-checkin tables (teacher quick-record per child/day):
  - GrowthTemplate / GrowthTemplateOption  (quick-pick dimensions/options)
  - GrowthCheckin / GrowthCheckinItem

AI report tables (per-child daily/weekly reports generated in batch):
  - ReportBatch / ChildReport

Content security (WeChat msg_sec_check / media_check_async verdicts):
  - ContentScan

All models share the Base/metadata in ai_teacher.storage.database.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    TIMESTAMP,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_teacher.storage.database import Base
from ai_teacher.storage.models import Homework


# --------- Auth / classes ---------

class User(Base):
    """A WeChat user. Can be parent or teacher."""

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    openid: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # 'parent' | 'teacher'
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)
    last_login: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    classes_teaching: Mapped[list["Classroom"]] = relationship(
        back_populates="teacher"
    )


class Classroom(Base):
    """A class owned by a teacher. Parents join with a 6-digit code."""

    __tablename__ = "classroom"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)

    teacher: Mapped[User] = relationship(back_populates="classes_teaching")
    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="classroom", cascade="all, delete-orphan"
    )


class Membership(Base):
    """A parent's enrollment. Stores the child name they uploaded for."""

    __tablename__ = "membership"
    __table_args__ = (
        UniqueConstraint("user_id", "classroom_id", name="uq_membership_user_class"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classroom.id", ondelete="CASCADE"), nullable=False
    )
    child_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)

    user: Mapped[User] = relationship()
    classroom: Mapped[Classroom] = relationship(back_populates="memberships")


class AuthToken(Base):
    """Bearer token; the mini program keeps it in local storage."""

    __tablename__ = "auth_token"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    user: Mapped[User] = relationship()


# Attach Homework <-> User/Classroom relationships here. The columns are plain
# integers (no schema-level FK), so give SQLAlchemy explicit join conditions.
# add_property must run before the mappers are first configured (first query).
Homework.__mapper__.add_property(
    "submit_user",
    relationship(
        User,
        primaryjoin="Homework.submit_user_id == User.id",
        foreign_keys=[Homework.submit_user_id],
    ),
)
Homework.__mapper__.add_property(
    "classroom",
    relationship(
        Classroom,
        primaryjoin="Homework.classroom_id == Classroom.id",
        foreign_keys=[Homework.classroom_id],
        back_populates="homeworks",
    ),
)
Classroom.__mapper__.add_property(
    "homeworks",
    relationship(
        Homework,
        primaryjoin="Homework.classroom_id == Classroom.id",
        foreign_keys=[Homework.classroom_id],
        back_populates="classroom",
    ),
)


# --------- Growth checkin templates ---------

class GrowthTemplate(Base):
    """A quick-record dimension (meal / nap / mood / ...).

    classroom_id NULL means a system-builtin template available to every class.
    """

    __tablename__ = "growth_template"
    __table_args__ = (
        UniqueConstraint("classroom_id", "code", name="uq_template_class_code"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    classroom_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("classroom.id", ondelete="CASCADE"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    multi_select: Mapped[int] = mapped_column(Integer, default=1)  # 0/1
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[int] = mapped_column(Integer, default=1)

    options: Mapped[list["GrowthTemplateOption"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="GrowthTemplateOption.sort_order",
    )


class GrowthTemplateOption(Base):
    """A tappable option under a dimension (e.g. 吃光啦 / 有点挑食)."""

    __tablename__ = "growth_template_option"
    __table_args__ = (
        UniqueConstraint("template_id", "label", name="uq_template_option_label"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("growth_template.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    template: Mapped[GrowthTemplate] = relationship(back_populates="options")


# --------- Growth checkin records ---------

class GrowthCheckin(Base):
    """One teacher record for one child on one day (whole-class scoped)."""

    __tablename__ = "growth_checkin"
    __table_args__ = (
        UniqueConstraint(
            "classroom_id", "child_name", "checkin_date",
            name="uq_checkin_class_child_date",
        ),
        Index("ix_checkin_class_date", "classroom_id", "checkin_date"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classroom.id", ondelete="CASCADE"), nullable=False
    )
    child_name: Mapped[str] = mapped_column(String(64), nullable=False)
    teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    checkin_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.now, onupdate=datetime.now
    )

    items: Mapped[list["GrowthCheckinItem"]] = relationship(
        back_populates="checkin",
        cascade="all, delete-orphan",
        order_by="GrowthCheckinItem.id",
    )


class GrowthCheckinItem(Base):
    """One selected option inside a daily checkin (multi-select -> rows)."""

    __tablename__ = "growth_checkin_item"
    __table_args__ = (
        UniqueConstraint(
            "checkin_id", "category_code", "option_label",
            name="uq_checkin_item",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    checkin_id: Mapped[int] = mapped_column(
        ForeignKey("growth_checkin.id", ondelete="CASCADE"), nullable=False
    )
    category_code: Mapped[str] = mapped_column(String(16), nullable=False)
    option_label: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)

    checkin: Mapped[GrowthCheckin] = relationship(back_populates="items")


# --------- AI daily/weekly reports ---------

class ReportBatch(Base):
    """A batch run: one class, one day/week, one report per child."""

    __tablename__ = "report_batch"
    __table_args__ = (
        UniqueConstraint(
            "classroom_id", "report_type", "period_start",
            name="uq_batch_class_type_start",
        ),
        CheckConstraint("report_type in ('day', 'week')", name="ck_batch_type"),
        CheckConstraint(
            "status in ('pending', 'running', 'done', 'partial', 'failed')",
            name="ck_batch_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classroom.id", ondelete="CASCADE"), nullable=False
    )
    teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    report_type: Mapped[str] = mapped_column(String(8), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)

    reports: Mapped[list["ChildReport"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ChildReport.id",
    )


class ChildReport(Base):
    """AI-generated report for one child in one batch; teacher edits/publishes."""

    __tablename__ = "child_report"
    __table_args__ = (
        UniqueConstraint("batch_id", "child_name", name="uq_report_batch_child"),
        UniqueConstraint(
            "classroom_id", "child_name", "report_type", "period_start",
            name="uq_report_child_period",
        ),
        CheckConstraint("report_type in ('day', 'week')", name="ck_report_type"),
        CheckConstraint(
            "status in ('pending', 'running', 'done', 'failed')",
            name="ck_report_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("report_batch.id", ondelete="CASCADE"), nullable=False
    )
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classroom.id", ondelete="CASCADE"), nullable=False
    )
    child_name: Mapped[str] = mapped_column(String(64), nullable=False)
    report_type: Mapped[str] = mapped_column(String(8), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # AI draft
    teacher_edit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # final version
    is_published: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    error_msg: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.now, onupdate=datetime.now
    )

    batch: Mapped[ReportBatch] = relationship(back_populates="reports")


class ContentScan(Base):
    """One WeChat content-security verdict for a piece of text or media.

    Media checks (media_check_async) are asynchronous: a row starts as
    ``pending`` with ``trace_id`` and is updated by the /api/wx/notify
    callback. A separate table (rather than columns on homework/report)
    keeps create_all sufficient on existing SQLite/Oracle DBs.
    """

    __tablename__ = "content_scan"
    __table_args__ = (
        Index("ix_content_scan_target", "target_type", "target_id"),
        Index("ix_content_scan_trace", "trace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    # 'user_text' | 'homework_text' | 'homework_media' | 'report_text'
    # | 'checkin_text'
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 'text' | 'image' | 'voice' | 'video'
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="text")
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # 'pending' | 'pass' | 'review' | 'risky' | 'error' | 'skipped'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    openid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.now, onupdate=datetime.now
    )


ALL_NEW_TABLES = [
    User,
    Classroom,
    Membership,
    AuthToken,
    GrowthTemplate,
    GrowthTemplateOption,
    GrowthCheckin,
    GrowthCheckinItem,
    ReportBatch,
    ChildReport,
    ContentScan,
]
