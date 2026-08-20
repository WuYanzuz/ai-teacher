"""Image helpers: compress, base64-encode, size check."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image

from ..utils.config import get_settings
from ..utils.logger import get_logger

log = get_logger()
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def compress_image(
    src: Path,
    dst: Optional[Path] = None,
    *,
    max_dim: int | None = None,
    quality: int | None = None,
) -> Path:
    """Compress an image to a JPEG under max_dim. Returns the path written."""
    settings = get_settings()
    max_dim = max_dim or settings.media("image_max_dim", 2048)
    quality = quality or settings.media("image_quality", 85)

    if dst is None:
        dst = src.with_suffix(".jpg")

    img = Image.open(src)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Resize if too large
    w, h = img.size
    if max(w, h) > max_dim:
        if w >= h:
            new_w = max_dim
            new_h = int(h * max_dim / w)
        else:
            new_h = max_dim
            new_w = int(w * max_dim / h)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    img.save(dst, format="JPEG", quality=quality, optimize=True)
    log.debug(f"compressed {src.name} -> {dst.name} ({dst.stat().st_size//1024}KB)")
    return dst


def to_base64_jpeg(path: Path) -> str:
    """Read an image file and return a base64-encoded data URL."""
    if not is_image(path):
        raise ValueError(f"not an image: {path}")
    img = Image.open(path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def ensure_size_under_limit(path: Path, max_mb: float | None = None) -> Path:
    settings = get_settings()
    max_mb = max_mb or settings.media("image_max_mb", 20)
    if path.stat().st_size <= max_mb * 1024 * 1024:
        return path
    log.info(f"{path.name} > {max_mb}MB, recompressing")
    return compress_image(path)
