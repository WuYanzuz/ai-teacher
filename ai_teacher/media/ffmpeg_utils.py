"""Shared ffmpeg/ffmpeg_utils helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _find_ffmpeg() -> str | None:
    """Try system PATH first, then the imageio-ffmpeg bundled binary."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def require_ffmpeg() -> str:
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found. Options:\n"
            "  1) Install via winget:  winget install Gyan.FFmpeg\n"
            "  2) pip install imageio-ffmpeg  (bundled, no admin needed)\n"
            "  3) Download from https://www.gyan.dev/ffmpeg/builds/ and add to PATH"
        )
    return ffmpeg


def file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)
