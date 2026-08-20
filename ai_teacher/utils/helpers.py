"""Cross-cutting helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


def short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def safe_filename(name: str, default: str = "file") -> str:
    """Strip path separators and dangerous chars from a filename."""
    keep = []
    for ch in name:
        if ch.isalnum() or ch in ("_", "-", "."):
            keep.append(ch)
        else:
            keep.append("_")
    out = "".join(keep).strip("._") or default
    return out[:80]


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p
