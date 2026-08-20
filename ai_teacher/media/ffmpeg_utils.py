"""Shared ffmpeg/ffprobe utilities."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found. Install it and make sure it's on PATH. "
            "Windows: download from https://www.gyan.dev/ffmpeg/builds/ "
            "and add to PATH."
        )
    return ffmpeg


def file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)
