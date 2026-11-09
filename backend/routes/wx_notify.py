"""WeChat server callbacks: signature echo + media_check_async results.

Configure in mp console (设置与开发 → 基本配置 → 服务器地址):
  URL  = https://<your-domain>/api/wx/notify
  Token = WX_MSG_TOKEN in .env
  消息加解密方式 = 明文模式 or 兼容模式 (safe/encrypted mode is not supported yet)

The async media verdict arrives as an XML event push:
  MsgType=event, Event=wxa_media_check, trace_id + result.suggest/label.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from ai_teacher.storage.database import session_scope
from ai_teacher.utils.logger import get_logger

from ..config import get_settings
from ..services import wx_security

log = get_logger()
router = APIRouter(tags=["wx-notify"])


def _signature_ok(signature: str, timestamp: str, nonce: str) -> bool:
    token = get_settings().wx_msg_token
    if not token or not signature:
        return False
    digest = hashlib.sha1(
        "".join(sorted([token, timestamp, nonce])).encode("utf-8")
    ).hexdigest()
    return digest == signature


def _require_configured() -> None:
    if not get_settings().wx_msg_token:
        raise HTTPException(503, "WX_MSG_TOKEN not configured")


@router.get("/api/wx/notify")
def wx_notify_verify(
    signature: str = "",
    timestamp: str = "",
    nonce: str = "",
    echostr: str = "",
):
    """WeChat server URL verification: echo echostr back when signature matches."""
    _require_configured()
    if not _signature_ok(signature, timestamp, nonce):
        raise HTTPException(403, "bad signature")
    return PlainTextResponse(echostr)


@router.post("/api/wx/notify")
async def wx_notify_event(
    request: Request,
    signature: str = "",
    timestamp: str = "",
    nonce: str = "",
):
    _require_configured()
    if not _signature_ok(signature, timestamp, nonce):
        raise HTTPException(403, "bad signature")

    body = (await request.body()).decode("utf-8", errors="ignore")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        log.warning("wx_notify: unparseable XML")
        return PlainTextResponse("success")

    if root.findtext("MsgType") != "event":
        return PlainTextResponse("success")
    if root.findtext("Event") != "wxa_media_check":
        return PlainTextResponse("success")

    trace_id = root.findtext("trace_id") or ""
    suggest = (
        root.findtext("result/suggest")
        or root.findtext(".//suggest")
        or "pass"
    )
    label = root.findtext("result/label") or root.findtext(".//label")

    try:
        with session_scope() as db:
            n = wx_security.apply_media_result(
                db,
                trace_id=trace_id,
                suggest=suggest,
                label=(label or None),
                detail=body,
            )
        log.info(f"media_check callback trace={trace_id} verdict={suggest} rows={n}")
    except Exception:
        log.exception("failed to apply media_check callback")
        # Let WeChat retry the push.
        raise HTTPException(500, "processing failed")

    return PlainTextResponse("success")
