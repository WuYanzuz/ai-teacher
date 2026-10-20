"""Batch AI report generation: state machine + per-child LLM calls.

Lifecycle
  ReportBatch:  pending -> running -> done | partial | failed
  ChildReport: pending -> running -> done | failed

Rules:
  - Only one run per batch: status CAS pending -> running (double-click safe).
  - Each child is an independent short transaction; one failure doesn't kill
    the batch.
  - No DB session is held open while the LLM call is in flight.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from ai_teacher.storage.database import session_scope
from ai_teacher.storage.models import Homework
from ai_teacher.utils.logger import get_logger

from ..models import (
    ChildReport,
    Classroom,
    GrowthCheckin,
    GrowthTemplate,
    Membership,
    ReportBatch,
)
from .report_prompts import SYSTEM_PROMPT, build_user_prompt, period_range

log = get_logger()

BATCH_TERMINAL = ("done", "partial", "failed")


class ReportConflict(Exception):
    """Raised when regeneration is blocked by published reports."""


# ---------- startup recovery ----------

def recover_interrupted() -> None:
    """Mark batches/reports stuck in pending/running as failed after a restart.

    BackgroundTasks don't survive process death; the teacher can regenerate.
    """
    with session_scope() as db:
        db.execute(
            update(ReportBatch)
            .where(ReportBatch.status.in_(["pending", "running"]))
            .values(status="failed", error_msg="服务重启,任务中断,请重新生成", finished_at=datetime.now())
        )
        db.execute(
            update(ChildReport)
            .where(ChildReport.status.in_(["pending", "running"]))
            .values(status="failed", error_msg="服务重启,任务中断")
        )


# ---------- batch creation ----------

def class_children(db, class_id: int) -> list[str]:
    return db.scalars(
        select(Membership.child_name)
        .where(Membership.classroom_id == class_id)
        .distinct()
        .order_by(Membership.child_name)
    ).all()


def create_batch(
    db,
    *,
    class_id: int,
    teacher_id: int,
    report_type: str,
    anchor,
    regenerate: bool,
) -> tuple[ReportBatch, bool]:
    """Create (or return existing) batch + per-child pending rows.

    Returns (batch, is_new). Caller schedules run_batch only when is_new.
    """
    start, end = period_range(report_type, anchor)
    existing = db.scalar(
        select(ReportBatch).where(
            ReportBatch.classroom_id == class_id,
            ReportBatch.report_type == report_type,
            ReportBatch.period_start == start,
        )
    )
    if existing is not None:
        if not regenerate:
            return existing, False
        published = db.scalar(
            select(func.count())
            .select_from(ChildReport)
            .where(ChildReport.batch_id == existing.id, ChildReport.is_published == 1)
        )
        if published:
            raise ReportConflict("已有发布给家长的报告,请先撤回再重新生成")
        db.delete(existing)
        db.flush()

    children = class_children(db, class_id)
    batch = ReportBatch(
        classroom_id=class_id,
        teacher_id=teacher_id,
        report_type=report_type,
        period_start=start,
        period_end=end,
        status="pending",
        total=len(children),
        succeeded=0,
        failed_count=0,
    )
    db.add(batch)
    db.flush()
    for name in children:
        db.add(ChildReport(
            batch_id=batch.id,
            classroom_id=class_id,
            child_name=name,
            report_type=report_type,
            period_start=start,
            period_end=end,
            status="pending",
        ))
    db.commit()
    db.refresh(batch)
    return batch, True


# ---------- background execution ----------

def run_batch(batch_id: int) -> None:
    """Background entry point. CAS-guarded; processes every pending child."""
    # Claim the batch exactly once.
    with session_scope() as db:
        result = db.execute(
            update(ReportBatch)
            .where(ReportBatch.id == batch_id, ReportBatch.status == "pending")
            .values(status="running", started_at=datetime.now())
        )
        claimed = result.rowcount > 0
        if not claimed:
            log.info(f"batch {batch_id}: not pending, skip")
            return
        reports = db.scalars(
            select(ChildReport.id)
            .where(ChildReport.batch_id == batch_id, ChildReport.status == "pending")
            .order_by(ChildReport.id)
        ).all()

    try:
        text_client = _make_text_client()
    except Exception as e:
        log.exception(f"batch {batch_id}: text client unavailable")
        _fail_all(batch_id, reports, f"AI 服务不可用: {e}")
        return

    for rid in reports:
        try:
            _generate_one(rid, text_client)
        except Exception as e:
            log.exception(f"batch {batch_id}: report {rid} crashed")
            _mark_report(rid, "failed", error_msg=str(e)[:1000])
    _finalize_batch(batch_id)


def retry_report(report_id: int) -> None:
    """Background entry point for retrying one failed child report."""
    with session_scope() as db:
        r = db.get(ChildReport, report_id)
        if r is None or r.status != "pending":
            return
        batch_id = r.batch_id
    # Keep status pending: _generate_one claims it via CAS pending->running.
    try:
        text_client = _make_text_client()
        _generate_one(report_id, text_client)
    except Exception as e:
        log.exception(f"retry report {report_id} crashed")
        _mark_report(report_id, "failed", error_msg=str(e)[:1000])
    _finalize_batch(batch_id)


def _generate_one(report_id: int, text_client) -> None:
    """Gather facts (no LLM), call the model, write the result."""
    with session_scope() as db:
        r = db.get(ChildReport, report_id)
        # CAS: only runnable from pending.
        if r is None or r.status != "pending":
            return
        claimed = db.execute(
            update(ChildReport)
            .where(ChildReport.id == report_id, ChildReport.status == "pending")
            .values(status="running")
        ).rowcount > 0
        if not claimed:
            return
        checkins, feedbacks = _gather_facts(db, r)
        report_type = r.report_type
        start, end = r.period_start, r.period_end

    user_prompt = build_user_prompt(report_type, start, end, checkins, feedbacks)
    content = text_client.chat(
        SYSTEM_PROMPT, user_prompt, temperature=0.5, max_tokens=2048
    )
    content = (content or "").strip()
    if not content:
        raise RuntimeError("AI 返回为空")

    with session_scope() as db:
        r = db.get(ChildReport, report_id)
        r.status = "done"
        r.content = content
        r.error_msg = None


def _gather_facts(db, r: ChildReport):
    label_rows = db.execute(
        select(GrowthTemplate.code, GrowthTemplate.label)
        .where(GrowthTemplate.classroom_id.is_(None))
    ).all()
    labels = {code: label for code, label in label_rows}

    ck_rows = db.scalars(
        select(GrowthCheckin)
        .options(selectinload(GrowthCheckin.items))
        .where(
            GrowthCheckin.classroom_id == r.classroom_id,
            GrowthCheckin.child_name == r.child_name,
            GrowthCheckin.checkin_date >= r.period_start,
            GrowthCheckin.checkin_date <= r.period_end,
        )
        .order_by(GrowthCheckin.checkin_date)
    ).all()
    checkins = [
        {
            "date": c.checkin_date,
            "note": c.note,
            "items": [
                {
                    "category_code": it.category_code,
                    "category_label": labels.get(it.category_code, it.category_code),
                    "options": [x.option_label for x in c.items
                                if x.category_code == it.category_code and x.option_label],
                    "note": it.note,
                }
                # one dict per (category) — dedupe below
                for it in {x.category_code: x for x in c.items}.values()
            ],
        }
        for c in ck_rows
    ]

    hw_rows = db.scalars(
        select(Homework)
        .where(
            Homework.classroom_id == r.classroom_id,
            Homework.child_name == r.child_name,
            Homework.is_homework == 1,
            Homework.feedback.is_not(None),
            Homework.feedback != "",
            Homework.created_at >= datetime.combine(r.period_start, time.min),
            Homework.created_at <= datetime.combine(r.period_end, time.max),
        )
        .order_by(Homework.created_at)
        .limit(10)
    ).all()
    feedbacks = [
        {"date": h.created_at.date(), "feedback": h.feedback or ""}
        for h in hw_rows
    ]
    return checkins, feedbacks


def _make_text_client():
    from ai_teacher.ai.deepseek_client import TextClient
    return TextClient()


# ---------- status helpers ----------

def _mark_report(report_id: int, status: str, *, error_msg: Optional[str] = None) -> None:
    with session_scope() as db:
        r = db.get(ChildReport, report_id)
        if r is None:
            return
        r.status = status
        if error_msg is not None:
            r.error_msg = error_msg[:1000]


def _fail_all(batch_id: int, report_ids: list[int], error_msg: str) -> None:
    with session_scope() as db:
        db.execute(
            update(ChildReport)
            .where(ChildReport.id.in_(report_ids))
            .values(status="failed", error_msg=error_msg[:1000])
        )
        db.execute(
            update(ReportBatch)
            .where(ReportBatch.id == batch_id)
            .values(
                status="failed",
                failed_count=len(report_ids),
                error_msg=error_msg[:1000],
                finished_at=datetime.now(),
            )
        )


def _finalize_batch(batch_id: int) -> None:
    with session_scope() as db:
        counts = dict(
            db.execute(
                select(ChildReport.status, func.count())
                .where(ChildReport.batch_id == batch_id)
                .group_by(ChildReport.status)
            ).all()
        )
        total = sum(counts.values())
        succeeded = counts.get("done", 0)
        failed = counts.get("failed", 0)
        pending = counts.get("pending", 0) + counts.get("running", 0)
        if pending:
            return  # still work in flight (e.g. single retry while others pending)
        if failed == 0:
            status = "done"
        elif succeeded > 0:
            status = "partial"
        else:
            status = "failed"
        db.execute(
            update(ReportBatch)
            .where(ReportBatch.id == batch_id)
            .values(
                status=status,
                total=total,
                succeeded=succeeded,
                failed_count=failed,
                finished_at=datetime.now(),
            )
        )
