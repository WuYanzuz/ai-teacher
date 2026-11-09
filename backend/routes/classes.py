"""Classroom routes: create (teacher), list, join (parent)."""

from __future__ import annotations

import random
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_teacher.storage.database import get_db

from ..auth import current_user
from ..models import Classroom, Membership, User
from ..services import wx_security

router = APIRouter(prefix="/api/classes", tags=["classes"])


def _gen_code() -> str:
    """6-digit join code, easy to type."""
    return "".join(random.choices(string.digits, k=6))


class CreateClassReq(BaseModel):
    name: str


class JoinClassReq(BaseModel):
    code: str
    child_name: str


class ClassOut(BaseModel):
    id: int
    name: str
    code: str
    teacher_name: str
    member_count: int
    role: str  # 'teacher' or 'parent' (caller's role in this class)
    child_name: Optional[str] = None  # if parent


def _to_out(db: Session, c: Classroom, caller: User) -> ClassOut:
    member_count = db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.classroom_id == c.id)
    ) or 0
    role = "teacher" if c.teacher_id == caller.id else "parent"
    child_name = None
    if role == "parent":
        m = db.scalar(
            select(Membership).where(
                Membership.user_id == caller.id,
                Membership.classroom_id == c.id,
            )
        )
        if m:
            child_name = m.child_name
    return ClassOut(
        id=c.id, name=c.name, code=c.code,
        teacher_name=c.teacher.name, member_count=member_count,
        role=role, child_name=child_name,
    )


@router.post("", response_model=ClassOut)
def create_class(req: CreateClassReq, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role != "teacher":
        raise HTTPException(403, "only teachers can create classes")
    code = _gen_code()
    while db.scalar(select(Classroom.id).where(Classroom.code == code)):
        code = _gen_code()
    c = Classroom(name=req.name, code=code, teacher=user, created_at=datetime.now())
    db.add(c)
    db.commit()
    db.refresh(c)
    return _to_out(db, c, user)


@router.get("", response_model=list[ClassOut])
def list_classes(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role == "teacher":
        cs = db.scalars(
            select(Classroom)
            .where(Classroom.teacher_id == user.id)
            .order_by(Classroom.id)
        ).all()
    else:
        # parent: classes I've joined
        cs = db.scalars(
            select(Classroom)
            .join(Membership, Membership.classroom_id == Classroom.id)
            .where(Membership.user_id == user.id)
            .order_by(Classroom.id)
        ).all()
    return [_to_out(db, c, user) for c in cs]


@router.post("/join", response_model=ClassOut)
def join_class(req: JoinClassReq, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role != "parent":
        raise HTTPException(403, "only parents can join classes")
    c = db.scalar(select(Classroom).where(Classroom.code == req.code))
    if not c:
        raise HTTPException(404, "invalid class code")
    child_name = (req.child_name or "").strip()
    if not child_name:
        raise HTTPException(400, "child name cannot be empty")
    wx_security.guard_text(
        db,
        target_type=wx_security.TARGET_USER_TEXT,
        target_id=user.id,
        text=child_name,
        openid=user.openid,
        scene=wx_security.SCENE_PROFILE,
    )
    existing = db.scalar(
        select(Membership.id).where(
            Membership.user_id == user.id,
            Membership.classroom_id == c.id,
        )
    )
    if not existing:
        db.add(Membership(
            user=user, classroom=c,
            child_name=child_name, created_at=datetime.now(),
        ))
        db.commit()
    return _to_out(db, c, user)


@router.get("/{class_id}/children")
def list_children(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Distinct child names in the class (both parents joining merge to one)."""
    c = db.get(Classroom, class_id)
    if not c:
        raise HTTPException(404, "class not found")
    if user.role == "teacher" and c.teacher_id != user.id:
        raise HTTPException(403, "not your class")
    if user.role == "parent":
        m = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.classroom_id == c.id,
            )
        )
        if not m:
            raise HTTPException(403, "not a member")
    names = db.scalars(
        select(Membership.child_name)
        .where(Membership.classroom_id == class_id)
        .distinct()
        .order_by(Membership.child_name)
    ).all()
    return {"class_id": class_id, "children": names}


@router.get("/{class_id}", response_model=ClassOut)
def get_class(class_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = db.get(Classroom, class_id)
    if not c:
        raise HTTPException(404, "class not found")
    if user.role == "teacher" and c.teacher_id != user.id:
        raise HTTPException(403, "not your class")
    if user.role == "parent":
        m = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.classroom_id == c.id,
            )
        )
        if not m:
            raise HTTPException(403, "not a member")
    return _to_out(db, c, user)
