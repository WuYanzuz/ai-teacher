"""Child growth report route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_teacher.storage import db as storage_db
from ai_teacher.storage.database import get_db
from ai_teacher.storage.models import Child

from ..auth import current_user
from ..models import Classroom, Membership, User

router = APIRouter(prefix="/api/children", tags=["children"])


@router.get("/{child_name}/report")
def get_report(
    child_name: str,
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    c = db.get(Classroom, class_id)
    if not c:
        raise HTTPException(404, "class not found")
    if user.role == "teacher" and c.teacher_id != user.id:
        raise HTTPException(403, "forbidden")
    if user.role == "parent":
        m = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.classroom_id == c.id,
            )
        )
        if not m:
            raise HTTPException(403, "forbidden")
        if m.child_name != child_name:
            raise HTTPException(403, "not your child")

    child = db.scalars(
        select(Child).where(Child.name == child_name).order_by(Child.id)
    ).first()
    if not child:
        raise HTTPException(404, "no history for this child")

    history = storage_db.child_history(child, limit=10)
    return {
        "child_name": child_name,
        "history": history,
        "total": len(history),
    }
