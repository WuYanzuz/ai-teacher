"""Video: ffmpeg keyframe extraction."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..utils.config import get_settings
from ..utils.logger import get_logger

log = get_logger()
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def _which_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH")
    return ffmpeg


def extract_frames(
    video_path: Path,
    out_dir: Path,
    *,
    n_frames: int | None = None,
    fps: int | None = None,
    scale: int | None = None,
) -> list[Path]:
    """Extract n keyframes from a video. Returns the list of JPEG paths."""
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    settings = get_settings()
    n_frames = n_frames or settings.media("video_frames", 6)
    fps = fps or settings.media("video_fps", 1)
    scale = scale or settings.media("video_scale", 720)

    out_dir.mkdir(parents=True, exist_ok=True)
    # Cleanup any previous frames
    for old in out_dir.glob(f"{video_path.stem}_*.jpg"):
        old.unlink()

    ffmpeg = _which_ffmpeg()
    pattern = out_dir / f"{video_path.stem}_%02d.jpg"
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-vf", f"fps={fps},scale={scale}:-2",
        "-frames:v", str(n_frames),
        "-q:v", "3",
        str(pattern),
    ]
    log.debug(f"ffmpeg frames: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error(f"ffmpeg stderr:\n{proc.stderr}")
        raise RuntimeError(f"extract_frames failed for {video_path}")

    frames = sorted(out_dir.glob(f"{video_path.stem}_*.jpg"))
    log.info(f"extracted {len(frames)} frames from {video_path.name}")
    return frames


def video_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0
