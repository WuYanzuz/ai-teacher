"""Classroom routes: create (teacher), list, join (parent)."""

from __future__ import annotations

import random
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import current_user
from ..models import Classroom, Membership, User

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


def _to_out(c: Classroom, caller: User) -> ClassOut:
    """Build a ClassOut from a Classroom + the calling user."""
    teacher_name = c.teacher.name
    member_count = Membership.select().where(Membership.classroom == c).count()
    role = "teacher" if c.teacher.id == caller.id else "parent"
    child_name = None
    if role == "parent":
        m = Membership.get_or_none(
            (Membership.user == caller) & (Membership.classroom == c)
        )
        if m:
            child_name = m.child_name
    return ClassOut(
        id=c.id, name=c.name, code=c.code,
        teacher_name=teacher_name, member_count=member_count,
        role=role, child_name=child_name,
    )


@router.post("", response_model=ClassOut)
def create_class(req: CreateClassReq, user: User = Depends(current_user)):
    if user.role != "teacher":
        raise HTTPException(403, "only teachers can create classes")
    code = _gen_code()
    while Classroom.get_or_none(Classroom.code == code):
        code = _gen_code()
    c = Classroom.create(name=req.name, code=code, teacher=user, created_at=datetime.now())
    return _to_out(c, user)


@router.get("", response_model=list[ClassOut])
def list_classes(user: User = Depends(current_user)):
    if user.role == "teacher":
        cs = list(Classroom.select().where(Classroom.teacher == user))
    else:
        # parent: classes I've joined
        my_memberships = Membership.select().where(Membership.user == user)
        cs = [m.classroom for m in my_memberships]
    return [_to_out(c, user) for c in cs]


@router.post("/join", response_model=ClassOut)
def join_class(req: JoinClassReq, user: User = Depends(current_user)):
    if user.role != "parent":
        raise HTTPException(403, "only parents can join classes")
    c = Classroom.get_or_none(Classroom.code == req.code)
    if not c:
        raise HTTPException(404, "invalid class code")
    Membership.get_or_create(
        user=user, classroom=c,
        defaults={"child_name": req.child_name, "created_at": datetime.now()},
    )
    return _to_out(c, user)


@router.get("/{class_id}", response_model=ClassOut)
def get_class(class_id: int, user: User = Depends(current_user)):
    c = Classroom.get_or_none(Classroom.id == class_id)
    if not c:
        raise HTTPException(404, "class not found")
    if user.role == "teacher" and c.teacher.id != user.id:
        raise HTTPException(403, "not your class")
    if user.role == "parent":
        m = Membership.get_or_none(
            (Membership.user == user) & (Membership.classroom == c)
        )
        if not m:
            raise HTTPException(403, "not a member")
    return _to_out(c, user)
