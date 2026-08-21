"""Backend config (extends ai_teacher Settings)."""

from __future__ import annotations

import os
from ai_teacher.utils.config import get_settings as _get_ai_settings


def get_settings():
    s = _get_ai_settings()
    # WeChat Mini Program credentials (for code2session)
    s.wx_appid = os.getenv("WX_APPID", "")
    s.wx_secret = os.getenv("WX_SECRET", "")
    s.upload_dir = s.cache_dir.parent / "uploads"
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    return s
