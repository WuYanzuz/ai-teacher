"""Vision model router.

Picks the right vision client at startup based on config.yaml.
All clients share the same interface so the dispatcher doesn't care.

Supported providers:
  - "aliyun"  : Aliyun Bailian OpenAI-compatible endpoint (qwen-vl-plus etc.)
  - "doubao"  : Volcano Ark OpenAI-compatible endpoint (doubao vision models)
  - "qwen"    : Alibaba DashScope native SDK (qwen-vl-max etc.)
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


def _build(provider: str) -> VisionClient:
    """Construct a vision client for the given provider name."""
    provider = provider.lower()

    if provider in ("aliyun", "bailian", "dashscope-openai"):
        from .openai_vl_client import build_aliyun_vl_client
        log.info("vision provider: Aliyun Bailian (OpenAI-compatible)")
        return build_aliyun_vl_client()

    if provider in ("doubao", "volc", "volcano"):
        try:
            from .openai_vl_client import build_volcano_vl_client
            log.info("vision provider: Volcano Ark (OpenAI-compatible)")
            return build_volcano_vl_client()
        except Exception as e:
            log.warning(f"Volcano VL init failed ({e}), fallback to Aliyun")
            from .openai_vl_client import build_aliyun_vl_client
            return build_aliyun_vl_client()

    # Default: Aliyun Bailian (OpenAI-compatible)
    from .openai_vl_client import build_aliyun_vl_client
    log.info("vision provider: Aliyun Bailian (default)")
    return build_aliyun_vl_client()


def get_vision_client() -> VisionClient:
    """Lazy singleton. Reads config.yaml -> models.vision.provider."""
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    provider = (settings.model("vision") or {}).get("provider", "aliyun")
    _client = _build(provider)
    return _client
