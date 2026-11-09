"""WeChat content security: msg_sec_check (text) + media_check_async (media).

The mini program handles user-uploaded media and teacher-written text, so
platform content moderation is required before release. This module wraps
WeChat's two security APIs and persists every verdict in ``content_scan``.

Design
------
- Text checks are synchronous. Call sites use :func:`guard_text`, which
  records the verdict and raises HTTP 400 on ``risky``. ``review`` is
  allowed — the teacher remains the human gate before parents see anything.
- Media checks are asynchronous. :func:`scan_homework_media` submits the
  file and stores ``trace_id``; the result arrives later at
  ``/api/wx/notify`` (see routes/wx_notify.py) and is matched by trace_id.
- Fail-open: without WX_APPID/WX_SECRET (local dev) or while the API is
  unreachable, checks return SKIPPED/ERROR and never block the product.
  Every such case is logged so a production outage stays visible.
"""

from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_teacher.media.ffmpeg_utils import require_ffmpeg
from ai_teacher.media.video import video_duration
from ai_teacher.storage.database import session_scope
from ai_teacher.storage.models import Homework
from ai_teacher.utils.logger import get_logger

from ..config import get_settings
from ..models import ContentScan

log = get_logger()

WX_BASE = "https://api.weixin.qq.com"

# msg_sec_check / media_check_async scene codes:
# 1 资料  2 评论  3 论坛  4 社交日志
SCENE_PROFILE = 1
SCENE_COMMENT = 2

# target_type values (also the content_scan.target_type column)
TARGET_USER_TEXT = "user_text"
TARGET_HOMEWORK_TEXT = "homework_text"
TARGET_HOMEWORK_MEDIA = "homework_media"
TARGET_REPORT_TEXT = "report_text"
TARGET_CHECKIN_TEXT = "checkin_text"

# media_check_async media_type codes
_MEDIA_TYPE_CODE = {"image": 1, "voice": 2}

_MSG_CHUNK = 2000          # msg_sec_check limit is 2500 chars
_HTTP_TIMEOUT = 10


@dataclass
class Verdict:
    status: str  # pass | review | risky | pending | error | skipped
    label: Optional[str] = None
    trace_id: Optional[str] = None
    detail: Optional[str] = None
    errmsg: Optional[str] = None


# ---------- access_token (process-local cache, thread-safe) ----------

_token_lock = threading.Lock()
_token_cache: dict = {"value": None, "expires_at": 0.0}


def _fetch_access_token() -> str:
    s = get_settings()
    if not s.wx_appid or not s.wx_secret:
        raise RuntimeError("WX_APPID/WX_SECRET not configured")
    r = requests.get(
        f"{WX_BASE}/cgi-bin/token",
        params={
            "grant_type": "client_credential",
            "appid": s.wx_appid,
            "secret": s.wx_secret,
        },
        timeout=_HTTP_TIMEOUT,
    )
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"access_token error: {data}")
    _token_cache["value"] = token
    # Refresh 5 minutes before the official 7200s expiry.
    _token_cache["expires_at"] = time.time() + int(data.get("expires_in", 7200)) - 300
    return token


def _access_token(force: bool = False) -> Optional[str]:
    s = get_settings()
    if not s.wx_appid or not s.wx_secret:
        return None
    with _token_lock:
        if force or time.time() >= _token_cache["expires_at"]:
            return _fetch_access_token()
        return _token_cache["value"]


def _post_json(path: str, payload: dict) -> dict:
    """POST JSON to a WeChat API, refreshing the token once on auth errors."""
    def _do(token: str) -> dict:
        r = requests.post(
            f"{WX_BASE}{path}",
            params={"access_token": token},
            json=payload,
            timeout=_HTTP_TIMEOUT,
        )
        return r.json()

    token = _access_token()
    if token is None:
        return {"errcode": -1, "errmsg": "wx credentials missing"}
    data = _do(token)
    if data.get("errcode") in (40001, 40014, 42001):  # invalid/expired token
        log.warning("access_token rejected by WeChat, refreshing once")
        data = _do(_access_token(force=True))
    return data


# ---------- text (msg_sec_check v2, synchronous) ----------

def check_text(text: str, *, openid: str, scene: int = SCENE_COMMENT) -> Verdict:
    """Check one text. Long texts are checked in chunks; worst verdict wins."""
    text = (text or "").strip()
    if not text:
        return Verdict("pass")
    if _access_token() is None:
        return Verdict("skipped", errmsg="wx credentials missing")

    worst = Verdict("pass")
    rank = {"pass": 0, "review": 1, "risky": 2, "error": 0, "skipped": 0}
    for i in range(0, len(text), _MSG_CHUNK):
        payload = {
            "version": 2,
            "scene": scene,
            "openid": openid or "",
            "content": text[i:i + _MSG_CHUNK],
        }
        try:
            data = _post_json("/wxa/msg_sec_check", payload)
        except requests.RequestException as e:
            log.warning(f"msg_sec_check request failed: {e}")
            v = Verdict("error", errmsg=str(e))
        else:
            if data.get("errcode") != 0:
                log.warning(f"msg_sec_check errcode={data.get('errcode')} {data.get('errmsg')}")
                v = Verdict("error", errmsg=data.get("errmsg"))
            else:
                result = data.get("result") or {}
                v = Verdict(
                    status=result.get("suggest", "pass"),
                    label=str(result.get("label")) if result.get("label") is not None else None,
                    trace_id=result.get("trace_id"),
                    detail=str(data)[:2000],
                )
        if rank.get(v.status, 0) > rank.get(worst.status, 0):
            worst = v
        if worst.status == "risky":
            break
    return worst


def guard_text(
    db: Session,
    *,
    target_type: str,
    target_id: int,
    text: str,
    openid: str,
    scene: int = SCENE_COMMENT,
    kind: str = "text",
) -> Optional[Verdict]:
    """Check text, persist the verdict, raise 400 when it is risky.

    Error/skipped verdicts are logged but do not block (fail-open).
    """
    text = (text or "").strip()
    if not text:
        return None
    v = check_text(text, openid=openid or "", scene=scene)
    if v.status in ("pass", "review", "risky"):
        record_scan(db, target_type=target_type, target_id=target_id,
                    kind=kind, verdict=v, openid=openid)
    if v.status == "risky":
        raise HTTPException(400, "内容可能包含违规信息，请修改后再提交")
    return v


# ---------- media (media_check_async, result comes via callback) ----------

def _absolute_media_url(media_path: str) -> Optional[str]:
    s = get_settings()
    if not s.public_base_url or not media_path:
        return None
    p = Path(media_path)
    upload_root = Path(s.upload_dir)
    try:
        rel = p.relative_to(upload_root).as_posix()
    except ValueError:
        log.warning(f"media outside upload dir, cannot submit: {media_path}")
        return None
    return f"{s.public_base_url}/media/{rel}"


def _extract_middle_frame(video_path: Path) -> Path:
    """media_check_async takes image/voice only, so submit one frame for video."""
    s = get_settings()
    out_dir = Path(s.upload_dir) / "moderation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{uuid.uuid4().hex}.jpg"
    mid = max(0.0, video_duration(video_path) / 2.0)
    base_cmd = [
        require_ffmpeg(), "-y",
        "-ss", f"{mid:.2f}",
        "-i", str(video_path),
        "-frames:v", "1", "-q:v", "3",
        str(out),
    ]
    proc = subprocess.run(base_cmd, capture_output=True, timeout=60)
    if proc.returncode != 0 or not out.exists():
        # Some files seek poorly mid-stream; retry from the start.
        base_cmd[3] = "0.00"
        subprocess.run(base_cmd, capture_output=True, timeout=60)
    if not out.exists():
        raise RuntimeError(f"frame extraction failed for {video_path.name}")
    return out


def submit_media(
    *, media_url: str, kind: str, openid: str, scene: int = SCENE_COMMENT
) -> Verdict:
    """Submit image/voice for an async check. Video frames are submitted as images."""
    if _access_token() is None:
        return Verdict("skipped", errmsg="wx credentials missing")
    media_type = _MEDIA_TYPE_CODE.get(kind)
    if media_type is None:
        return Verdict("skipped", errmsg=f"unsupported kind: {kind}")
    payload = {
        "media_url": media_url,
        "media_type": media_type,
        "version": 2,
        "scene": scene,
        "openid": openid or "",
    }
    try:
        data = _post_json("/wxa/media_check_async", payload)
    except requests.RequestException as e:
        log.warning(f"media_check_async request failed: {e}")
        return Verdict("error", errmsg=str(e))
    if data.get("errcode") != 0:
        log.warning(f"media_check_async errcode={data.get('errcode')} {data.get('errmsg')}")
        return Verdict("error", errmsg=data.get("errmsg"))
    return Verdict("pending", trace_id=data.get("trace_id"), detail=str(data)[:2000])


def scan_homework_media(hw_id: int) -> None:
    """Background task: submit a homework's media for moderation.

    Videos are represented by one middle frame. Runs in its own DB session;
    never raises (a moderation outage must not break homework processing).
    """
    try:
        with session_scope() as db:
            hw = db.get(Homework, hw_id)
            if hw is None:
                return
            kind = hw.media_type
            media_path = hw.media_path
            openid = hw.submit_user.openid if hw.submit_user_id else ""

        if kind not in ("image", "voice", "video") or not media_path:
            return
        frame_path: Optional[Path] = None
        if kind == "video":
            frame_path = _extract_middle_frame(Path(media_path))
            url = _absolute_media_url(str(frame_path))
            submit_kind = "image"
        else:
            url = _absolute_media_url(media_path)
            submit_kind = kind
        if not url:
            log.info("PUBLIC_BASE_URL not set; skipping media moderation submission")
            return
        v = submit_media(media_url=url, kind=submit_kind, openid=openid or "")
        with session_scope() as db:
            record_scan(
                db,
                target_type=TARGET_HOMEWORK_MEDIA,
                target_id=hw_id,
                kind=kind,
                verdict=v,
                openid=openid,
            )
    except Exception:
        log.exception(f"scan_homework_media failed for homework {hw_id}")


def scan_homework_text(hw_id: int) -> None:
    """Background task: check the AI-produced feedback text after the pipeline."""
    try:
        with session_scope() as db:
            hw = db.get(Homework, hw_id)
            if hw is None or not hw.feedback:
                return
            openid = hw.submit_user.openid if hw.submit_user_id else ""
            v = check_text(hw.feedback, openid=openid, scene=SCENE_COMMENT)
            if v.status in ("pass", "review", "risky"):
                record_scan(
                    db,
                    target_type=TARGET_HOMEWORK_TEXT,
                    target_id=hw_id,
                    kind="text",
                    verdict=v,
                    openid=openid,
                )
    except Exception:
        log.exception(f"scan_homework_text failed for homework {hw_id}")


# ---------- persistence ----------

def record_scan(
    db: Session,
    *,
    target_type: str,
    target_id: int,
    kind: str,
    verdict: Verdict,
    openid: Optional[str] = None,
) -> ContentScan:
    row = ContentScan(
        target_type=target_type,
        target_id=target_id,
        kind=kind,
        trace_id=verdict.trace_id,
        status=verdict.status,
        label=verdict.label,
        detail=verdict.detail,
        openid=openid,
    )
    db.add(row)
    db.flush()
    return row


def _latest_rows(db: Session, target_type: str, target_ids: list[int]) -> dict[int, ContentScan]:
    """Most recent scan row per target id."""
    if not target_ids:
        return {}
    rows = db.scalars(
        select(ContentScan)
        .where(
            ContentScan.target_type == target_type,
            ContentScan.target_id.in_(target_ids),
        )
        .order_by(ContentScan.target_id, ContentScan.id.desc())
    ).all()
    latest: dict[int, ContentScan] = {}
    for r in rows:
        latest.setdefault(r.target_id, r)
    return latest


def risky_ids(db: Session, target_type: str, target_ids: list[int]) -> set[int]:
    return {tid for tid, row in _latest_rows(db, target_type, target_ids).items()
            if row.status == "risky"}


def homework_moderation(db: Session, hw_ids: list[int]) -> dict[int, dict]:
    """{hw_id: {"media": status, "text": status}} for rows with a verdict."""
    out: dict[int, dict] = {}
    for target_type, key in (
        (TARGET_HOMEWORK_MEDIA, "media"),
        (TARGET_HOMEWORK_TEXT, "text"),
    ):
        for tid, row in _latest_rows(db, target_type, hw_ids).items():
            out.setdefault(tid, {})[key] = row.status
    return out


def apply_media_result(
    db: Session, *, trace_id: str, suggest: str, label: Optional[str], detail: str
) -> int:
    """Apply a media_check_async callback. Returns rows updated."""
    if not trace_id:
        return 0
    rows = db.scalars(
        select(ContentScan).where(ContentScan.trace_id == trace_id)
    ).all()
    for r in rows:
        r.status = suggest if suggest in ("pass", "review", "risky") else "pass"
        r.label = label
        if detail:
            r.detail = (detail or "")[:4000]
    db.flush()
    return len(rows)
