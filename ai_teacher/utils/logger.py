"""Logger setup based on loguru."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .config import get_settings

_configured = False


def get_logger():
    """Return a configured loguru logger (idempotent)."""
    global _configured
    if _configured:
        return logger

    settings = get_settings()
    log_dir: Path = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    level = settings.log_cfg.get("level", "INFO")
    rotation = settings.log_cfg.get("rotation", "100 MB")
    retention = settings.log_cfg.get("retention", "30 days")

    # Console (colored)
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>",
    )

    # Rotated file
    logger.add(
        log_dir / "ai_teacher_{time:YYYY-MM-DD}.log",
        level=level,
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        enqueue=True,
    )

    _configured = True
    return logger
