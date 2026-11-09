"""Homework routes: parent uploads, teacher lists/views/acks/renames."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_teacher.storage.database import get_db, session_scope
from ai_teacher.storage.models import Child, Homework
from ai_teacher.utils.logger import get_logger

from ..auth import current_user
from ..config import get_settings
from ..models import Classroom, Membership, User
from ..services import wx_security
from ..services.ai_pipeline import process_homework
from ..services.storage import save_upload

log = get_logger()

router = APIRouter(prefix="/api/homework", tags=["homework"])


class HomeworkOut(BaseModel):
    id: int
    child_name: str
    media_type: str
    media_url: Optional[str] = None
    transcript: Optional[str] = None
    is_homework: bool
    raw_feedback: Optional[str] = None
    polished_feedback: Optional[str] = None
    teacher_review: Optional[str] = None
    created_at: str
    submitter_name: str
    # Latest content-security verdicts, e.g. {"media": "pass", "text": "pass"}
    moderation: Optional[dict] = None


class RenameReq(BaseModel):
    child_name: str


class EditFeedbackReq(BaseModel):
    feedback: str


# ---------- Parent: upload ----------

@router.post("/upload", response_model=HomeworkOut)
def upload_homework(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    class_id: int = Form(...),
    child_name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role != "parent":
        raise HTTPException(403, "only parents upload homework")
    m = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.classroom_id == class_id,
        )
    )
    if not m:
        raise HTTPException(403, "not a member of this class")
    child_name = child_name.strip()
    if not child_name:
        raise HTTPException(400, "child name cannot be empty")
    # Synchronous text moderation on the free-text child name.
    wx_security.guard_text(
        db,
        target_type=wx_security.TARGET_USER_TEXT,
        target_id=user.id,
        text=child_name,
        openid=user.openid,
        scene=wx_security.SCENE_PROFILE,
    )
    suffix = Path(file.filename or "").suffix.lower() or ".bin"
    content = file.file.read()
    if len(content) > 100 * 1024 * 1024:  # 100MB cap
        raise HTTPException(413, "file too large (max 100MB)")
    local_path, public_url = save_upload(content, suffix)
    child_id = _get_or_make_child_id(db, user.openid, child_name)
    hw = Homework(
        child_id=child_id,
        group_roomid=f"class:{class_id}",
        msg_id=int(time.time() * 1000),  # synthetic
        media_type=_media_kind(suffix),
        media_path=str(local_path),
        raw_transcript=None,
        is_homework=0,
        feedback=None,
        submit_user_id=user.id,
        classroom_id=class_id,
        child_name=child_name,
        created_at=datetime.now(),
    )
    db.add(hw)
    db.commit()
    db.refresh(hw)
    # Build the response before the background task runs; only pass the id.
    # Background tasks run in registration order: AI pipeline first, then the
    # feedback text check; media submission is independent and goes last.
    out = _to_out(db, hw, m, public_url)
    background.add_task(_process_async, hw.id, local_path, child_name)
    background.add_task(wx_security.scan_homework_text, hw.id)
    background.add_task(wx_security.scan_homework_media, hw.id)
    return out


def _process_async(hw_id: int, file_path: Path, child_name: str) -> None:
    """Background task: run AI pipeline, update the Homework row."""
    try:
        # Slow AI call happens with no DB session held open.
        result = process_homework(file_path, child_name)
        with session_scope() as db:
            hw = db.get(Homework, hw_id)
            if hw is None:
                log.warning(f"background: homework {hw_id} vanished")
                return
            if result.get("error"):
                hw.feedback = f"[处理失败] {result['error']}"
            else:
                hw.is_homework = 1 if result.get("is_homework") else 0
                hw.raw_transcript = result.get("transcript")
                hw.feedback = (
                    result.get("polished_feedback")
                    or result.get("raw_feedback")
                    or ""
                )
    except Exception as e:
        log.exception(f"background processing failed for homework {hw_id}")
        try:
            with session_scope() as db:
                hw = db.get(Homework, hw_id)
                if hw is not None:
                    hw.feedback = f"[处理异常] {e}"
        except Exception:
            pass


# ---------- Teacher: list, view, ack, rename, ignore ----------

@router.get("", response_model=list[HomeworkOut])
def list_homework(
    class_id: int,
    only_homework: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    c = db.get(Classroom, class_id)
    if not c:
        raise HTTPException(404, "class not found")
    _require_class_member(db, c, user)
    stmt = select(Homework).where(Homework.classroom_id == class_id)
    if user.role == "parent":
        # Parents only ever see their own submissions, never classmates'.
        stmt = stmt.where(Homework.submit_user_id == user.id)
    if only_homework:
        stmt = stmt.where(Homework.is_homework == 1)
    stmt = stmt.order_by(Homework.created_at.desc()).limit(100)
    rows = db.scalars(stmt).all()
    moderation = wx_security.homework_moderation(db, [hw.id for hw in rows])
    risky = {tid for tid, mo in moderation.items() if "risky" in mo.values()}
    out = []
    for hw in rows:
        # Risky content is hidden from parents; the teacher still sees it flagged.
        if user.role == "parent" and hw.id in risky:
            continue
        out.append(_to_out(db, hw, None, _build_media_url(hw.media_path),
                           moderation=moderation.get(hw.id)))
    return out


@router.get("/{hw_id}", response_model=HomeworkOut)
def get_homework(
    hw_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if not _can_view(db, hw, user):
        raise HTTPException(403, "forbidden")
    moderation = wx_security.homework_moderation(db, [hw.id]).get(hw.id)
    if user.role == "parent" and moderation and "risky" in moderation.values():
        raise HTTPException(404, "not found")
    return _to_out(db, hw, None, _build_media_url(hw.media_path),
                   moderation=moderation)


@router.post("/{hw_id}/rename", response_model=HomeworkOut)
def rename_child(
    hw_id: int,
    req: RenameReq,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if not _is_class_teacher(db, hw.classroom_id, user):
        raise HTTPException(403, "forbidden")
    new_name = req.child_name.strip()
    if not new_name:
        raise HTTPException(400, "child name cannot be empty")
    if hw.child is not None:
        hw.child.name = new_name
    hw.child_name = new_name
    db.commit()
    return get_homework(hw_id, db, user)


@router.post("/{hw_id}/ack", response_model=HomeworkOut)
def ack(
    hw_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if not _is_class_teacher(db, hw.classroom_id, user):
        raise HTTPException(403, "forbidden")
    hw.teacher_review = "✓ 已确认"
    db.commit()
    return get_homework(hw_id, db, user)


@router.post("/{hw_id}/ignore", response_model=HomeworkOut)
def ignore(
    hw_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if not _is_class_teacher(db, hw.classroom_id, user):
        raise HTTPException(403, "forbidden")
    hw.is_homework = 0
    db.commit()
    return get_homework(hw_id, db, user)


@router.post("/{hw_id}/feedback", response_model=HomeworkOut)
def edit_feedback(
    hw_id: int,
    req: EditFeedbackReq,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Teacher edits the feedback text. The new text overrides the AI's."""
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if not _is_class_teacher(db, hw.classroom_id, user):
        raise HTTPException(403, "forbidden")
    new_text = (req.feedback or "").strip()
    if not new_text:
        raise HTTPException(400, "feedback cannot be empty")
    wx_security.guard_text(
        db,
        target_type=wx_security.TARGET_HOMEWORK_TEXT,
        target_id=hw.id,
        text=new_text,
        openid=user.openid,
        scene=wx_security.SCENE_COMMENT,
    )
    if not hw.teacher_review or "已编辑" not in hw.teacher_review:
        hw.teacher_review = "✏️ 已编辑"
    hw.feedback = new_text
    db.commit()
    return get_homework(hw_id, db, user)


@router.post("/{hw_id}/reset_feedback", response_model=HomeworkOut)
def reset_feedback(
    hw_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Mark as not-edited (no revert of the actual text in this MVP)."""
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if not _is_class_teacher(db, hw.classroom_id, user):
        raise HTTPException(403, "forbidden")
    hw.teacher_review = None
    db.commit()
    return get_homework(hw_id, db, user)


# ---------- permission helpers ----------

def _require_class_member(db: Session, c: Classroom, user: User) -> None:
    if user.role == "teacher":
        if c.teacher_id != user.id:
            raise HTTPException(403, "not your class")
        return
    m = db.scalar(
        select(Membership.id).where(
            Membership.user_id == user.id,
            Membership.classroom_id == c.id,
        )
    )
    if not m:
        raise HTTPException(403, "not a member")


def _is_class_teacher(db: Session, classroom_id: Optional[int], user: User) -> bool:
    if user.role != "teacher" or classroom_id is None:
        return False
    teacher_id = db.scalar(
        select(Classroom.teacher_id).where(Classroom.id == classroom_id)
    )
    return teacher_id == user.id


def _can_view(db: Session, hw: Homework, user: User) -> bool:
    if user.role == "teacher":
        return _is_class_teacher(db, hw.classroom_id, user)
    if user.role == "parent":
        return hw.submit_user_id == user.id
    return False


# ---------- output / misc helpers ----------

def _media_kind(suffix: str) -> str:
    s = suffix.lower()
    if s in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        return "image"
    if s in (".mp4", ".mov", ".mkv", ".avi", ".m4v"):
        return "video"
    if s in (".mp3", ".wav", ".m4a", ".silk", ".ogg"):
        return "voice"
    return "file"


def _get_or_make_child_id(db: Session, parent_openid: str, child_name: str) -> int:
    """Find or create the global Child row (name-based, as in the old code)."""
    child = db.scalar(select(Child).where(Child.name == child_name))
    if child is None:
        now = datetime.now()
        child = Child(
            name=child_name,
            parent_wxid=parent_openid or None,
            first_seen=now,
            last_seen=now,
        )
        db.add(child)
        db.flush()  # get child.id without ending the request transaction
    return child.id


def _resolve_child_name(db: Session, hw: Homework) -> str:
    if hw.child_name:
        return hw.child_name
    child = db.get(Child, hw.child_id) if hw.child_id else None
    return child.name if child else "?"


def _to_out(
    db: Session,
    hw: Homework,
    membership: Optional[Membership],
    media_url: Optional[str],
    moderation: Optional[dict] = None,
) -> HomeworkOut:
    child_name = hw.child_name
    if not child_name:
        child = db.get(Child, hw.child_id) if hw.child_id else None
        child_name = child.name if child else (membership.child_name if membership else "?")
    submitter = "?"
    if hw.submit_user_id is not None:
        u = db.get(User, hw.submit_user_id)
        if u is not None:
            submitter = u.name
    return HomeworkOut(
        id=hw.id,
        child_name=child_name,
        media_type=hw.media_type,
        media_url=media_url,
        transcript=hw.raw_transcript,
        is_homework=bool(hw.is_homework),
        raw_feedback=hw.feedback,
        polished_feedback=hw.feedback,
        teacher_review=hw.teacher_review,
        created_at=hw.created_at.isoformat() if hw.created_at else "",
        submitter_name=submitter,
        moderation=moderation,
    )


def _build_media_url(media_path: str | None) -> str | None:
    """Build a /media/... URL from an absolute filesystem path."""
    if not media_path:
        return None
    try:
        p = Path(media_path)
        upload_root = Path(get_settings().upload_dir)
        try:
            rel = p.relative_to(upload_root).as_posix()
        except ValueError:
            rel = p.name
        return f"/media/{rel}"
    except Exception:
        return None
