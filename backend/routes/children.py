"""Child growth report route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ai_teacher.storage import db as storage_db
from ai_teacher.storage.models import Child

from ..auth import current_user
from ..models import Classroom, Membership, User

router = APIRouter(prefix="/api/children", tags=["children"])


@router.get("/{child_name}/report")
def get_report(child_name: str, class_id: int, user: User = Depends(current_user)):
    c = Classroom.get_or_none(Classroom.id == class_id)
    if not c:
        raise HTTPException(404, "class not found")
    if user.role == "teacher" and c.teacher.id != user.id:
        raise HTTPException(403, "forbidden")
    if user.role == "parent":
        m = Membership.get_or_none(
            (Membership.user == user) & (Membership.classroom == c)
        )
        if not m:
            raise HTTPException(403, "forbidden")
        if m.child_name != child_name:
            raise HTTPException(403, "not your child")

    child = Child.get_or_none(
        (Child.name == child_name) & (Child.parent_wxid != "")
    )
    # Try alternative: any child with this name
    if not child:
        child = Child.get_or_none(Child.name == child_name)

    if not child:
        raise HTTPException(404, "no history for this child")

    history = storage_db.child_history(child, limit=10)
    return {
        "child_name": child_name,
        "history": history,
        "total": len(history),
    }
