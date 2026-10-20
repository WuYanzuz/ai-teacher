"""AI daily/weekly report routes: batch generate, edit, publish, view."""

from __future__ import annotations

from datetime import date as date_cls, datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_teacher.storage.database import get_db

from ..auth import current_user
from ..models import (
    ChildReport,
    Classroom,
    Membership,
    ReportBatch,
    User,
)
from ..services import report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ---------- schemas ----------

class CreateBatchReq(BaseModel):
    class_id: int
    type: str  # 'day' | 'week'
    date: date_cls
    regenerate: bool = False


class EditReportReq(BaseModel):
    content: str


# ---------- permission helpers ----------

def _owned_class(db: Session, class_id: int, user: User) -> Classroom:
    c = db.get(Classroom, class_id)
    if not c:
        raise HTTPException(404, "class not found")
    if user.role != "teacher" or c.teacher_id != user.id:
        raise HTTPException(403, "not your class")
    return c


def _parent_child(db: Session, class_id: int, user: User) -> Optional[str]:
    m = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.classroom_id == class_id,
        )
    )
    return m.child_name if m else None


# ---------- serializers ----------

def _batch_out(b: ReportBatch, only_child: Optional[str] = None) -> dict:
    reports = b.reports
    if only_child is not None:
        # Parents only see their own child's row, never classmates' names.
        reports = [r for r in reports if r.child_name == only_child]
    return {
        "id": b.id,
        "class_id": b.classroom_id,
        "report_type": b.report_type,
        "period_start": b.period_start.isoformat(),
        "period_end": b.period_end.isoformat(),
        "status": b.status,
        "total": b.total,
        "succeeded": b.succeeded,
        "failed_count": b.failed_count,
        "error_msg": b.error_msg,
        "started_at": b.started_at.isoformat() if b.started_at else None,
        "finished_at": b.finished_at.isoformat() if b.finished_at else None,
        "reports": [
            {
                "id": r.id,
                "child_name": r.child_name,
                "status": r.status,
                "error_msg": r.error_msg,
                "is_published": bool(r.is_published),
            }
            for r in reports
        ],
    }


def _report_out(r: ChildReport) -> dict:
    return {
        "id": r.id,
        "batch_id": r.batch_id,
        "class_id": r.classroom_id,
        "child_name": r.child_name,
        "report_type": r.report_type,
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "status": r.status,
        "content": r.content,
        "teacher_edit": r.teacher_edit,
        "visible_content": r.teacher_edit or r.content,
        "is_published": bool(r.is_published),
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "error_msg": r.error_msg,
    }


# ---------- batch routes ----------

@router.post("/batches")
def create_batch(
    req: CreateBatchReq,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if req.type not in ("day", "week"):
        raise HTTPException(400, "type must be 'day' or 'week'")
    _owned_class(db, req.class_id, user)
    if not report_service.class_children(db, req.class_id):
        raise HTTPException(400, "class has no children yet")
    try:
        batch, is_new = report_service.create_batch(
            db,
            class_id=req.class_id,
            teacher_id=user.id,
            report_type=req.type,
            anchor=req.date,
            regenerate=req.regenerate,
        )
    except report_service.ReportConflict as e:
        raise HTTPException(409, str(e))
    if is_new:
        background.add_task(report_service.run_batch, batch.id)
    return _batch_out(batch)


@router.get("/batches/{batch_id}")
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    b = db.get(ReportBatch, batch_id)
    if not b:
        raise HTTPException(404, "batch not found")
    if user.role == "teacher":
        _owned_class(db, b.classroom_id, user)
        return _batch_out(b)
    # Parents may poll their own child's row only.
    own = _parent_child(db, b.classroom_id, user)
    if not own:
        raise HTTPException(403, "not a member")
    return _batch_out(b, only_child=own)


@router.post("/batches/{batch_id}/publish_all")
def publish_all(
    batch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    b = db.get(ReportBatch, batch_id)
    if not b:
        raise HTTPException(404, "batch not found")
    _owned_class(db, b.classroom_id, user)
    now = datetime.now()
    count = 0
    for r in b.reports:
        if r.status == "done" and not r.is_published:
            r.is_published = 1
            r.published_at = now
            count += 1
    db.commit()
    return {"published": count}


# ---------- single report routes ----------

@router.get("/child")
def list_for_child(
    class_id: int,
    child_name: str,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Reports for one child. Parents see published reports for own child only."""
    if user.role == "teacher":
        _owned_class(db, class_id, user)
    else:
        own = _parent_child(db, class_id, user)
        if not own or own != child_name:
            raise HTTPException(403, "not your child")
    stmt = select(ChildReport).where(
        ChildReport.classroom_id == class_id,
        ChildReport.child_name == child_name,
    )
    if type in ("day", "week"):
        stmt = stmt.where(ChildReport.report_type == type)
    if user.role == "parent":
        stmt = stmt.where(ChildReport.is_published == 1)
    stmt = stmt.order_by(ChildReport.period_start.desc(), ChildReport.report_type)
    rows = db.scalars(stmt).all()
    return {"reports": [_report_out(r) for r in rows]}


@router.get("/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    r = db.get(ChildReport, report_id)
    if not r:
        raise HTTPException(404, "report not found")
    if user.role == "teacher":
        _owned_class(db, r.classroom_id, user)
    else:
        own = _parent_child(db, r.classroom_id, user)
        if not own or own != r.child_name or not r.is_published:
            raise HTTPException(403, "forbidden")
    return _report_out(r)


@router.post("/{report_id}/edit")
def edit_report(
    report_id: int,
    req: EditReportReq,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    r = db.get(ChildReport, report_id)
    if not r:
        raise HTTPException(404, "report not found")
    _owned_class(db, r.classroom_id, user)
    text = (req.content or "").strip()
    if not text:
        raise HTTPException(400, "content cannot be empty")
    r.teacher_edit = text
    db.commit()
    return _report_out(r)


@router.post("/{report_id}/publish")
def publish_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    r = db.get(ChildReport, report_id)
    if not r:
        raise HTTPException(404, "report not found")
    _owned_class(db, r.classroom_id, user)
    if r.status != "done":
        raise HTTPException(400, "report is not ready")
    r.is_published = 1
    r.published_at = datetime.now()
    db.commit()
    return _report_out(r)


@router.post("/{report_id}/unpublish")
def unpublish_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    r = db.get(ChildReport, report_id)
    if not r:
        raise HTTPException(404, "report not found")
    _owned_class(db, r.classroom_id, user)
    r.is_published = 0
    r.published_at = None
    db.commit()
    return _report_out(r)


@router.post("/{report_id}/retry")
def retry_report(
    report_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    r = db.get(ChildReport, report_id)
    if not r:
        raise HTTPException(404, "report not found")
    _owned_class(db, r.classroom_id, user)
    if r.status in ("pending", "running"):
        raise HTTPException(409, "report is still running")
    if r.is_published:
        raise HTTPException(409, "已发布的报告请先撤回再重试")
    # Requeue: back to pending, drop old draft.
    r.status = "pending"
    r.error_msg = None
    r.content = None
    r.is_published = 0
    r.published_at = None
    db.commit()
    background.add_task(report_service.retry_report, r.id)
    return _report_out(r)
