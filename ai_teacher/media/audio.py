"""Audio: convert WeChat .silk to wav and transcribe with Paraformer."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..utils.config import get_settings
from ..utils.logger import get_logger
from .ffmpeg_utils import require_ffmpeg

log = get_logger()


def _which_ffmpeg() -> str:
    return require_ffmpeg()


def silk_to_wav(silk_path: Path, out_dir: Path | None = None) -> Path:
    """Convert a WeChat .silk voice file to 16kHz mono wav.

    We rely on ffmpeg's built-in silk decoder (added in ffmpeg 4.4+). If the
    user's ffmpeg is too old, this will fail loudly.
    """
    if not silk_path.exists():
        raise FileNotFoundError(silk_path)

    out_dir = out_dir or silk_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / (silk_path.stem + ".wav")

    ffmpeg = _which_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-f", "silk",
        "-i", str(silk_path),
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        str(wav_path),
    ]
    log.debug(f"silk->wav: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not wav_path.exists():
        log.error(f"ffmpeg stderr:\n{proc.stderr}")
        raise RuntimeError(f"silk->wav failed for {silk_path}")
    return wav_path


def wav_duration(path: Path) -> float:
    """Get the duration of a wav file in seconds, via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # Fallback: assume 1KB ≈ 0.06s at 16kHz mono 16-bit
        return path.stat().st_size / 32000
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def transcribe(wav_path: Path) -> str:
    """Transcribe a wav file to text. Implemented as a thin wrapper that
    delegates to ai.paraformer_client. Importing locally to avoid a cycle."""
    from ..ai.paraformer_client import ParaformerClient

    client = ParaformerClient()
    return client.transcribe_file(wav_path)
