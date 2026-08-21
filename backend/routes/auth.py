"""Auth routes: WeChat login, dev login, /me."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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


@router.post("/wx_login", response_model=LoginResp)
def wx_login(req: WxLoginReq):
    """WeChat mini program login.

    1. Exchange code for openid via code2session
    2. Find or create user
    3. Issue bearer token
    """
    data = wx_code2session(req.code)
    openid = data["openid"]
    user, _ = User.get_or_create(
        openid=openid,
        defaults={"role": req.role, "name": req.name},
    )
    # Update name/role on subsequent logins (in case user toggles in UI)
    user.name = req.name or user.name
    if req.role in ("parent", "teacher"):
        user.role = req.role
    user.last_login = datetime.now()
    user.save()
    return LoginResp(token=issue_token(user), user=_user_dict(user))


@router.post("/dev_login", response_model=LoginResp)
def dev_login(req: DevLoginReq):
    """DEV-ONLY login without WeChat. Open access for local testing.

    DO NOT expose this in production. Set ENABLE_DEV_LOGIN=0 in .env to disable.
    """
    import os
    if os.getenv("ENABLE_DEV_LOGIN", "1") != "1":
        raise HTTPException(403, "dev login disabled")
    user, _ = User.get_or_create(
        openid=req.openid,
        defaults={"role": req.role, "name": req.name},
    )
    user.name = req.name
    user.last_login = datetime.now()
    user.save()
    return LoginResp(token=issue_token(user), user=_user_dict(user))


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
