"""Homework routes: parent uploads, teacher lists/views/acks/renames."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ai_teacher.storage.models import Homework

from ..auth import current_user
from ..models import Classroom, Membership, User
from ..services.ai_pipeline import process_homework
from ..services.storage import save_upload

router = APIRouter(prefix="/api/homework", tags=["homework"])


class HomeworkOut(BaseModel):
    id: int
    child_name: str
    media_type: str
    media_url: str
    transcript: Optional[str] = None
    is_homework: bool
    raw_feedback: Optional[str] = None
    polished_feedback: Optional[str] = None
    teacher_review: Optional[str] = None
    created_at: str
    submitter_name: str


class RenameReq(BaseModel):
    child_name: str


class AckReq(BaseModel):
    pass  # no body needed


class IgnoreReq(BaseModel):
    pass


class EditFeedbackReq(BaseModel):
    feedback: str


# ---------- Parent: upload ----------

@router.post("/upload", response_model=HomeworkOut)
def upload_homework(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    class_id: int = Form(...),
    child_name: str = Form(...),
    user: User = Depends(current_user),
):
    if user.role != "parent":
        raise HTTPException(403, "only parents upload homework")
    # Validate membership
    m = Membership.get_or_none(
        (Membership.user == user) & (Membership.classroom_id == class_id)
    )
    if not m:
        raise HTTPException(403, "not a member of this class")
    # Save file
    suffix = Path(file.filename or "").suffix.lower() or ".bin"
    content = file.file.read()
    if len(content) > 100 * 1024 * 1024:  # 100MB cap
        raise HTTPException(413, "file too large (max 100MB)")
    local_path, public_url = save_upload(content, suffix)
    # Create Homework row (mark as pending)
    from datetime import datetime
    hw = Homework.create(
        child_id=_get_or_make_child_id(m, child_name),
        group_roomid=f"class:{class_id}",
        msg_id=int(time.time() * 1000),  # synthetic
        media_type=_media_kind(suffix),
        media_path=str(local_path),
        raw_transcript=None,
        is_homework=0,
        feedback=None,
        submit_user=user,
        classroom_id=class_id,
        created_at=datetime.now(),
    )
    # Process in background
    background.add_task(_process_async, hw.id, local_path, child_name)
    return _to_out(hw, m, public_url)


def _process_async(hw_id: int, file_path: Path, child_name: str) -> None:
    """Background task: run AI pipeline, update Homework row."""
    try:
        result = process_homework(file_path, child_name)
        hw = Homework.get_by_id(hw_id)
        if result.get("error"):
            hw.feedback = f"[处理失败] {result['error']}"
        else:
            hw.is_homework = 1 if result.get("is_homework") else 0
            hw.raw_transcript = result.get("transcript")
            # Save both raw and polished: feedback = polished (sent to teacher);
            # we keep raw inside the message so teacher sees both if needed.
            polished = result.get("polished_feedback") or result.get("raw_feedback") or ""
            hw.feedback = polished
        hw.save()
    except Exception as e:
        try:
            hw = Homework.get_by_id(hw_id)
            hw.feedback = f"[处理异常] {e}"
            hw.save()
        except Exception:
            pass


# ---------- Teacher: list, view, ack, rename, ignore ----------

@router.get("", response_model=list[HomeworkOut])
def list_homework(
    class_id: int,
    only_homework: bool = True,
    user: User = Depends(current_user),
):
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
    qs = Homework.select().where(Homework.classroom == c)
    if only_homework:
        qs = qs.where(Homework.is_homework == 1)
    qs = qs.order_by(Homework.created_at.desc()).limit(100)
    out = []
    for hw in qs:
        # Build media URL
        media_url = None
        if hw.media_path:
            try:
                rel = hw.media_path.replace("\\", "/").split("/uploads/", 1)[1]
                media_url = f"/media/{rel}"
            except Exception:
                media_url = None
        submitter = hw.submit_user.name if hw.submit_user else "?"
        out.append(HomeworkOut(
            id=hw.id, child_name=hw.child.name if hw.child else "?",
            media_type=hw.media_type, media_url=media_url,
            transcript=hw.raw_transcript, is_homework=bool(hw.is_homework),
            raw_feedback=hw.feedback, polished_feedback=hw.feedback,
            teacher_review=hw.teacher_review,
            created_at=hw.created_at.isoformat() if hw.created_at else "",
            submitter_name=submitter,
        ))
    return out


@router.get("/{hw_id}", response_model=HomeworkOut)
def get_homework(hw_id: int, user: User = Depends(current_user)):
    hw = Homework.get_or_none(Homework.id == hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if not _can_view(hw, user):
        raise HTTPException(403, "forbidden")
    media_url = None
    if hw.media_path:
        try:
            rel = hw.media_path.replace("\\", "/").split("/uploads/", 1)[1]
            media_url = f"/media/{rel}"
        except Exception:
            pass
    return HomeworkOut(
        id=hw.id, child_name=hw.child.name if hw.child else "?",
        media_type=hw.media_type, media_url=media_url,
        transcript=hw.raw_transcript, is_homework=bool(hw.is_homework),
        raw_feedback=hw.feedback, polished_feedback=hw.feedback,
        teacher_review=hw.teacher_review,
        created_at=hw.created_at.isoformat() if hw.created_at else "",
        submitter_name=hw.submit_user.name if hw.submit_user else "?",
    )


@router.post("/{hw_id}/rename", response_model=HomeworkOut)
def rename_child(hw_id: int, req: RenameReq, user: User = Depends(current_user)):
    hw = Homework.get_or_none(Homework.id == hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if user.role != "teacher" or (hw.classroom and hw.classroom.teacher.id != user.id):
        raise HTTPException(403, "forbidden")
    if hw.child:
        hw.child.name = req.child_name
        hw.child.save()
    return get_homework(hw_id, user)


@router.post("/{hw_id}/ack", response_model=HomeworkOut)
def ack(hw_id: int, user: User = Depends(current_user)):
    hw = Homework.get_or_none(Homework.id == hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if user.role != "teacher" or (hw.classroom and hw.classroom.teacher.id != user.id):
        raise HTTPException(403, "forbidden")
    hw.teacher_review = "✓ 已确认"
    hw.save()
    return get_homework(hw_id, user)


@router.post("/{hw_id}/ignore", response_model=HomeworkOut)
def ignore(hw_id: int, user: User = Depends(current_user)):
    hw = Homework.get_or_none(Homework.id == hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if user.role != "teacher" or (hw.classroom and hw.classroom.teacher.id != user.id):
        raise HTTPException(403, "forbidden")
    hw.is_homework = 0
    hw.save()
    return get_homework(hw_id, user)


@router.post("/{hw_id}/feedback", response_model=HomeworkOut)
def edit_feedback(hw_id: int, req: EditFeedbackReq, user: User = Depends(current_user)):
    """Teacher edits the feedback text. The new text overrides the AI's output."""
    hw = Homework.get_or_none(Homework.id == hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if user.role != "teacher" or (hw.classroom and hw.classroom.teacher.id != user.id):
        raise HTTPException(403, "forbidden")
    new_text = (req.feedback or "").strip()
    if not new_text:
        raise HTTPException(400, "feedback cannot be empty")
    if not hw.teacher_review or "已编辑" not in hw.teacher_review:
        hw.teacher_review = "✏️ 已编辑"
    hw.feedback = new_text
    hw.save()
    return get_homework(hw_id, user)


@router.post("/{hw_id}/reset_feedback", response_model=HomeworkOut)
def reset_feedback(hw_id: int, user: User = Depends(current_user)):
    """Mark as not-edited (no revert of the actual text in this MVP)."""
    hw = Homework.get_or_none(Homework.id == hw_id)
    if not hw:
        raise HTTPException(404, "not found")
    if user.role != "teacher" or (hw.classroom and hw.classroom.teacher.id != user.id):
        raise HTTPException(403, "forbidden")
    hw.teacher_review = None
    hw.save()
    return get_homework(hw_id, user)


# ---------- helpers ----------

def _media_kind(suffix: str) -> str:
    s = suffix.lower()
    if s in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        return "image"
    if s in (".mp4", ".mov", ".mkv", ".avi", ".m4v"):
        return "video"
    if s in (".mp3", ".wav", ".m4a", ".silk", ".ogg"):
        return "voice"
    return "file"


def _get_or_make_child_id(membership: Membership, child_name: str) -> int:
    """Find or create a Child row for this parent's child name."""
    from datetime import datetime
    from ai_teacher.storage.models import Child
    child, _ = Child.get_or_create(
        name=child_name,
        defaults={
            "parent_wxid": membership.user.openid,
            "first_seen": datetime.now(),
            "last_seen": datetime.now(),
        },
    )
    return child.id


def _can_view(hw: Homework, user: User) -> bool:
    if user.role == "teacher":
        return hw.classroom is not None and hw.classroom.teacher.id == user.id
    if user.role == "parent":
        return hw.submit_user is not None and hw.submit_user.id == user.id
    return False


def _to_out(hw: Homework, membership: Membership, media_url: str) -> HomeworkOut:
    return HomeworkOut(
        id=hw.id,
        child_name=hw.child.name if hw.child else membership.child_name,
        media_type=hw.media_type,
        media_url=media_url,
        transcript=hw.raw_transcript,
        is_homework=bool(hw.is_homework),
        raw_feedback=hw.feedback,
        polished_feedback=hw.feedback,
        teacher_review=hw.teacher_review,
        created_at=hw.created_at.isoformat() if hw.created_at else "",
        submitter_name=membership.user.name,
    )
