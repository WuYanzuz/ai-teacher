"""AI pipeline service.

Wraps ai_teacher modules to process uploaded homework:
  - Image -> compress -> vision model -> grade
  - Video -> ffmpeg extract frames + audio -> asr -> vision -> grade
  - Voice -> silk -> wav -> asr -> grade

For MVP, runs synchronously. For production, queue with Celery/RQ.
"""

from __future__ import annotations

from pathlib import Path

from ai_teacher.media import audio as audio_mod
from ai_teacher.media import video as video_mod
from ai_teacher.media.image import compress_image, is_image
from ai_teacher.utils.config import get_settings
from ai_teacher.utils.helpers import safe_filename
from ai_teacher.utils.logger import get_logger

log = get_logger()
settings = get_settings()


def _extract_for_video(video_path: Path) -> tuple[list[Path], Path | None]:
    """Extract frames + audio from a video. Returns (frames, wav_path)."""
    out_dir = settings.cache_dir / f"mp_{safe_filename(video_path.stem)}_{int(__import__('time').time())}"
    frames = video_mod.extract_frames(video_path, out_dir)
    wav = out_dir / "audio.wav"
    try:
        from ai_teacher.media.ffmpeg_utils import require_ffmpeg
        import subprocess
        subprocess.run(
            [require_ffmpeg(), "-y", "-i", str(video_path), "-ar", "16000", "-ac", "1", str(wav)],
            check=False, capture_output=True,
        )
        if not wav.exists() or wav.stat().st_size < 1024:
            wav = None
    except Exception:
        wav = None
    return frames, wav


def process_homework(file_path: Path, child_name: str) -> dict:
    """Process an uploaded file: classify + grade + polish.

    Returns a dict: {
        "media_type": "image" | "video" | "voice",
        "is_homework": bool,
        "transcript": str | None,
        "raw_feedback": str,
        "polished_feedback": str,
        "error": str | None,
    }
    """
    try:
        from ai_teacher.ai.vision_router import get_vision_client
        from ai_teacher.ai.deepseek_client import TextClient
        from ai_teacher.ai.paraformer_client import ParaformerClient
    except Exception as e:
        return {"error": f"import failed: {e}"}

    if is_image(file_path):
        media_type = "image"
        if file_path.suffix.lower() not in (".jpg", ".jpeg"):
            compressed = compress_image(file_path)
        else:
            compressed = file_path
        frames = [compressed]
        transcript = None
    elif file_path.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".m4v"):
        media_type = "video"
        frames, wav = _extract_for_video(file_path)
        if not frames:
            return {"error": "video frame extraction failed", "media_type": "video"}
        transcript = None
        if settings.dashscope_api_key:
            try:
                transcript = ParaformerClient().transcribe_file(wav) if wav else None
            except Exception as e:
                log.warning(f"transcribe failed: {e}")
    elif file_path.suffix.lower() in (".mp3", ".wav", ".m4a", ".silk", ".ogg"):
        media_type = "voice"
        transcript = None
        if settings.dashscope_api_key:
            try:
                if file_path.suffix.lower() == ".silk":
                    wav = audio_mod.silk_to_wav(file_path)
                else:
                    wav = file_path
                transcript = ParaformerClient().transcribe_file(wav)
            except Exception as e:
                log.warning(f"transcribe failed: {e}")
        # Voice-only: synthesize a single "frame" for vision
        from PIL import Image
        frames = [Image.new("RGB", (16, 16), "white")]
    else:
        return {"error": f"unsupported file type: {file_path.suffix}", "media_type": "unknown"}

    # 1. Classify
    vl = get_vision_client()
    is_hw = vl.is_homework_image(frames[0], transcript=transcript)
    if not is_hw:
        return {
            "media_type": media_type, "is_homework": False,
            "transcript": transcript, "raw_feedback": None, "polished_feedback": None,
            "error": None,
        }

    # 2. Grade (only for image/video; voice uses transcript-based grading)
    if media_type == "voice":
        raw = _grade_audio(transcript or "")
    else:
        raw = vl.grade_homework(frames, transcript=transcript)

    # 3. Polish
    text = TextClient()
    try:
        polished = text.polish(raw)
    except Exception as e:
        log.warning(f"polish failed: {e}")
        polished = raw

    return {
        "media_type": media_type, "is_homework": True,
        "transcript": transcript, "raw_feedback": raw, "polished_feedback": polished,
        "error": None,
    }


def _grade_audio(transcript: str) -> str:
    """Score a voice-only homework using text model."""
    from ai_teacher.ai.deepseek_client import TextClient
    system = (
        "你是一名幼儿/小学低年级老师,正在点评孩子的朗读或口头作业。"
        "从清晰度、流畅度、完整度三个维度点评,并给 1-2 句鼓励。不超过 100 字。"
    )
    user = (
        f"孩子朗读/讲解转写: <<{transcript}>>\n\n"
        "按'亮点/建议/鼓励'三段输出。"
    )
    return TextClient().chat(system, user, temperature=0.5)
