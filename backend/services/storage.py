"""File storage service. Saves uploads to local disk, returns URL."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from ..config import get_settings


def save_upload(content: bytes, suffix: str, *, kind: str = "homework") -> tuple[Path, str]:
    """Save uploaded file, return (local_path, public_url_path).

    public_url_path is what the FastAPI app exposes to the mini program
    (e.g. '/media/20260821/<uuid>.jpg').
    """
    s = get_settings()
    day = time.strftime("%Y%m%d")
    folder = s.upload_dir / day
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{suffix}"
    path = folder / fname
    path.write_bytes(content)
    return path, f"/media/{day}/{fname}"
