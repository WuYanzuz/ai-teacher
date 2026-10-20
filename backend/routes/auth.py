"""Auth routes: WeChat login, dev login, /me."""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_teacher.storage.database import get_db

from ..auth import current_user, issue_token, wx_code2session
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class WxLoginReq(BaseModel):
    code: str
    role: str = "parent"  # 'parent' or 'teacher'
    name: str = "微信用户"


class DevLoginReq(BaseModel):
    openid: str
    name: str
    role: str = "parent"


class LoginResp(BaseModel):
    token: str
    user: dict


def _find_or_create_user(db: Session, openid: str, role: str, name: str) -> User:
    user = db.scalar(select(User).where(User.openid == openid))
    if user is None:
        user = User(openid=openid, role=role, name=name)
        db.add(user)
        db.flush()
    return user


@router.post("/wx_login", response_model=LoginResp)
def wx_login(req: WxLoginReq, db: Session = Depends(get_db)):
    """WeChat mini program login: code -> openid -> find/create user -> token."""
    data = wx_code2session(req.code)
    openid = data["openid"]
    user = _find_or_create_user(db, openid, req.role, req.name)
    # Update name/role on subsequent logins (in case user toggles in UI)
    user.name = req.name or user.name
    if req.role in ("parent", "teacher"):
        user.role = req.role
    user.last_login = datetime.now()
    db.commit()
    return LoginResp(token=issue_token(db, user), user=_user_dict(user))


@router.post("/dev_login", response_model=LoginResp)
def dev_login(req: DevLoginReq, db: Session = Depends(get_db)):
    """DEV-ONLY login without WeChat. Set ENABLE_DEV_LOGIN=0 to disable."""
    if os.getenv("ENABLE_DEV_LOGIN", "1") != "1":
        raise HTTPException(403, "dev login disabled")
    user = _find_or_create_user(db, req.openid, req.role, req.name)
    user.name = req.name
    user.last_login = datetime.now()
    db.commit()
    return LoginResp(token=issue_token(db, user), user=_user_dict(user))


@router.get("/me")
def me(user: User = Depends(current_user)):
    return _user_dict(user)


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "openid": user.openid,
        "role": user.role,
        "name": user.name,
        "avatar_url": user.avatar_url,
    }
