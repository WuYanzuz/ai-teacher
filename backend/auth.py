"""Auth helpers: tokens, WeChat code2session, dev login."""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from ai_teacher.storage.models import db

from .config import get_settings
from .models import AuthToken, User

settings = get_settings()


# ---------- Token ----------

def issue_token(user: User, ttl_days: int = 30) -> str:
    """Create a new auth token for the user."""
    token = secrets.token_urlsafe(32)
    AuthToken.create(
        token=token,
        user=user,
        created_at=datetime.now(),
        expires_at=datetime.now() + timedelta(days=ttl_days),
    )
    return token


def get_user_by_token(token: str) -> Optional[User]:
    """Resolve a bearer token to a User, or None if invalid/expired."""
    if not token:
        return None
    try:
        row = AuthToken.get(AuthToken.token == token)
    except AuthToken.DoesNotExist:
        return None
    if row.expires_at and row.expires_at < datetime.now():
        return None
    return row.user


# ---------- FastAPI dependency ----------

from fastapi import Header, HTTPException, status


async def current_user(authorization: Optional[str] = Header(None)) -> User:
    """FastAPI dependency: extract bearer token, return User or 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        )
    return user


# ---------- WeChat code2session ----------

def wx_code2session(code: str) -> dict:
    """Exchange WeChat wx.login() code for openid + session_key.

    See: https://developers.weixin.qq.com/miniprogram/dev/api-backend/open-api/login/auth.code2Session.html
    """
    appid = settings.wx_appid
    secret = settings.wx_secret
    if not appid or not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WeChat appid/secret not configured",
        )
    url = "https://api.weixin.qq.com/sns/jscode2session"
    r = requests.get(url, params={
        "appid": appid, "secret": secret, "js_code": code, "grant_type": "authorization_code",
    }, timeout=10)
    data = r.json()
    if "openid" not in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"WeChat login failed: {data.get('errmsg', data)}",
        )
    return data
