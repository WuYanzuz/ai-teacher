"""Backend config (extends ai_teacher Settings)."""

from __future__ import annotations

import os
from ai_teacher.utils.config import get_settings as _get_ai_settings


def get_settings():
    s = _get_ai_settings()
    # WeChat Mini Program credentials (for code2session)
    s.wx_appid = os.getenv("WX_APPID", "")
    s.wx_secret = os.getenv("WX_SECRET", "")
    # Token configured in mp console -> 消息推送; verifies security callbacks
    s.wx_msg_token = os.getenv("WX_MSG_TOKEN", "")
    # Public HTTPS origin, e.g. https://api.example.com
    # media_check_async can only fetch media via a publicly reachable URL
    s.public_base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    s.upload_dir = s.cache_dir.parent / "uploads"
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    return s
