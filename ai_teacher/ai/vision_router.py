"""Vision model router.

Picks between Qwen-VL and Doubao (Volcano) at startup based on config.
Both implementations share the same interface so callers don't care.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..utils.config import get_settings
from ..utils.logger import get_logger

log = get_logger()


class VisionClient(Protocol):
    def grade_images(self, image_paths, prompt: str, *, system: str | None = None) -> str: ...
    def is_homework_image(self, image_path: Path, transcript: str | None = None) -> bool: ...
    def grade_homework(self, image_paths: list[Path], transcript: str | None = None) -> str: ...


_client: VisionClient | None = None


def get_vision_client() -> VisionClient:
    """Lazy singleton.

    Choice order (config.yaml -> models.vision.provider):
      - "doubao" / "volc" / "volcano"  -> DoubaoVLClient
      - "qwen" / "dashscope" (default)  -> QwenVLClient
    """
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    provider = (settings.model("vision") or {}).get("provider", "qwen").lower()

    if provider in ("doubao", "volc", "volcano"):
        try:
            from .doubao_vl_client import DoubaoVLClient
            _client = DoubaoVLClient()
            log.info("vision provider: Doubao (Volcano Ark)")
        except Exception as e:
            log.warning(f"Doubao init failed ({e}), fallback to Qwen-VL")
            from .dashscope_client import QwenVLClient
            _client = QwenVLClient()
            log.info("vision provider: Qwen-VL (fallback)")
    else:
        from .dashscope_client import QwenVLClient
        _client = QwenVLClient()
        log.info("vision provider: Qwen-VL")
    return _client
