"""Daily growth check-in routes (teacher quick-record, parent view)."""

from __future__ import annotations

from datetime import date as date_cls
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_teacher.storage.database import get_db

from ..auth import current_user
from ..models import (
    Classroom,
    GrowthCheckin,
    GrowthCheckinItem,
    GrowthTemplate,
    Membership,
    User,
)

router = APIRouter(prefix="/api/checkin", tags=["checkin"])


# ---------- schemas ----------

class CheckinItemIn(BaseModel):
    category_code: str
    options: list[str] = []
    note: Optional[str] = None


class CheckinPutReq(BaseModel):
    class_id: int
    child_name: str
    date: date_cls
    note: Optional[str] = None
    items: list[CheckinItemIn] = []


# ---------- permission ----------

def _require_class(db: Session, class_id: int, user: User) -> Classroom:
    c = db.get(Classroom, class_id)
    if not c:
        raise HTTPException(404, "class not found")
    if user.role == "teacher":
        if c.teacher_id != user.id:
            raise HTTPException(403, "not your class")
        return c
    m = db.scalar(
        select(Membership.id).where(
            Membership.user_id == user.id,
            Membership.classroom_id == class_id,
        )
    )
    if not m:
        raise HTTPException(403, "not a member")
    return c


def _class_children(db: Session, class_id: int) -> list[str]:
    return db.scalars(
        select(Membership.child_name)
        .where(Membership.classroom_id == class_id)
        .distinct()
    ).all()


# ---------- serializers ----------

def _checkin_out(ck: GrowthCheckin) -> dict:
    by_cat: dict[str, dict] = {}
    for it in ck.items:
        cat = by_cat.setdefault(it.category_code, {"options": [], "note": None})
        if it.option_label:
            cat["options"].append(it.option_label)
        if it.note:
            cat["note"] = it.note
    return {
        "id": ck.id,
        "class_id": ck.classroom_id,
        "child_name": ck.child_name,
        "date": ck.checkin_date.isoformat(),
        "note": ck.note,
        "items": [
            {"category_code": code, **payload}
            for code, payload in sorted(by_cat.items())
        ],
    }


# ---------- routes ----------

@router.get("/template")
def get_template(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """System quick-record dimensions with their tappable options."""
    tpls = db.scalars(
        select(GrowthTemplate)
        .where(GrowthTemplate.classroom_id.is_(None), GrowthTemplate.active == 1)
        .order_by(GrowthTemplate.sort_order)
    ).all()
    return {
        "categories": [
            {
                "code": t.code,
                "label": t.label,
                "multi_select": bool(t.multi_select),
                "options": [o.label for o in t.options],
            }
            for t in tpls
        ]
    }


@router.get("/day")
def day_overview(
    class_id: int,
    date: date_cls,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Whole-class view for one day: which children have a check-in."""
    _require_class(db, class_id, user)
    checkins = db.scalars(
        select(GrowthCheckin).where(
            GrowthCheckin.classroom_id == class_id,
            GrowthCheckin.checkin_date == date,
        )
    ).all()
    by_name = {c.child_name: c for c in checkins}
    return {
        "class_id": class_id,
        "date": date.isoformat(),
        "children": [
            {
                "child_name": name,
                "done": name in by_name,
                "checkin_id": by_name[name].id if name in by_name else None,
            }
            for name in _class_children(db, class_id)
        ],
    }


@router.get("")
def get_checkin(
    class_id: int,
    date: date_cls,
    child_name: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """One child's check-in for a day (or 404)."""
    c = _require_class(db, class_id, user)
    if user.role == "parent":
        m = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.classroom_id == class_id,
            )
        )
        if m.child_name != child_name:
            raise HTTPException(403, "not your child")
    ck = db.scalar(
        select(GrowthCheckin).where(
            GrowthCheckin.classroom_id == class_id,
            GrowthCheckin.child_name == child_name,
            GrowthCheckin.checkin_date == date,
        )
    )
    if not ck:
        return {"id": None, "class_id": class_id, "child_name": child_name,
                "date": date.isoformat(), "note": None, "items": []}
    return _checkin_out(ck)


@router.put("")
def put_checkin(
    req: CheckinPutReq,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Teacher upserts one child's daily check-in (whole-day overwrite)."""
    if user.role != "teacher":
        raise HTTPException(403, "teacher only")
    c = db.get(Classroom, req.class_id)
    if not c or c.teacher_id != user.id:
        raise HTTPException(403, "not your class")
    name = req.child_name.strip()
    if name not in _class_children(db, req.class_id):
        raise HTTPException(400, "child is not in this class")

    ck = db.scalar(
        select(GrowthCheckin).where(
            GrowthCheckin.classroom_id == req.class_id,
            GrowthCheckin.child_name == name,
            GrowthCheckin.checkin_date == req.date,
        )
    )
    if ck is None:
        ck = GrowthCheckin(
            classroom_id=req.class_id,
            child_name=name,
            teacher_id=user.id,
            checkin_date=req.date,
        )
        db.add(ck)
    else:
        # Whole-group overwrite: remove old option rows, insert fresh ones.
        for old in list(ck.items):
            db.delete(old)
        ck.teacher_id = user.id
    ck.note = (req.note or "").strip() or None
    db.flush()

    for item in req.items:
        labels: list[str] = []
        for opt in item.options:
            opt = (opt or "").strip()
            if opt and opt not in labels:
                labels.append(opt)
        note = (item.note or "").strip() or None
        if not labels and not note:
            continue
        if labels:
            for label in labels:
                db.add(GrowthCheckinItem(
                    checkin_id=ck.id,
                    category_code=item.category_code,
                    option_label=label,
                    note=note,
                ))
        else:
            # Category-level note with no option picked.
            db.add(GrowthCheckinItem(
                checkin_id=ck.id,
                category_code=item.category_code,
                option_label="",
                note=note,
            ))

    db.commit()
    db.refresh(ck)
    return _checkin_out(ck)


@router.get("/child")
def child_checkins(
    class_id: int,
    child_name: str,
    start: date_cls,
    end: date_cls,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """A child's check-ins over a date range (parent: own child only)."""
    if start > end:
        raise HTTPException(400, "start must be <= end")
    _require_class(db, class_id, user)
    if user.role == "parent":
        m = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.classroom_id == class_id,
            )
        )
        if m.child_name != child_name:
            raise HTTPException(403, "not your child")
    rows = db.scalars(
        select(GrowthCheckin)
        .where(
            GrowthCheckin.classroom_id == class_id,
            GrowthCheckin.child_name == child_name,
            GrowthCheckin.checkin_date >= start,
            GrowthCheckin.checkin_date <= end,
        )
        .order_by(GrowthCheckin.checkin_date)
    ).all()
    return {
        "class_id": class_id,
        "child_name": child_name,
        "days": [_checkin_out(r) for r in rows],
    }
