"""Generic OpenAI-compatible vision-language client.

Works with any endpoint that speaks the OpenAI Chat Completions protocol and
accepts image inputs, e.g.:
  - 阿里百炼 (Aliyun Bailian) OpenAI-compatible endpoint
  - 火山方舟 (Volcano Ark) Plan endpoint
  - 任何其他 OpenAI 兼容服务

Image input is sent as base64 data URLs in the standard OpenAI image_url format.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Iterable

from openai import OpenAI

from ..utils.config import get_settings
from ..utils.logger import get_logger
from ..utils.retry import with_retry

log = get_logger()


def _file_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(suffix, "jpeg")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


class OpenAIVLClient:
    """OpenAI-compatible multimodal client. Configure via config.yaml."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> None:
        if not api_key:
            raise RuntimeError(f"api_key is empty for model={model}")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        log.info(f"vision client ready: model={model}, base={base_url[:50]}...")

    @with_retry(max_attempts=3, backoff=2.0, initial_delay=1.0)
    def grade_images(
        self,
        image_paths: Iterable[Path],
        prompt: str,
        *,
        system: str | None = None,
    ) -> str:
        content: list[dict] = []
        for p in image_paths:
            content.append({
                "type": "image_url",
                "image_url": {"url": _file_to_data_url(p)},
            })
        content.append({"type": "text", "text": prompt})

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})

        log.debug(f"calling VL model={self.model} images={len(image_paths)-1}")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content or ""

    def is_homework_image(self, image_path: Path, transcript: str | None = None) -> bool:
        """Return True if the image looks like a child's homework."""
        prompt = (
            "请判断这张图是否像是一份幼儿园/小学低年级孩子的作业。"
            "如果是家庭场景、聊天截图、表情包、营销内容,回答 NO。"
            "如果是手工作品、写字、算术、绘画、读绘本等作业,回答 YES。"
            "只回答 YES 或 NO,不要其他内容。"
        )
        if transcript:
            prompt += f"\n\n附加语音转写: {transcript}"
        try:
            txt = self.grade_images([image_path], prompt).strip().upper()
            return txt.startswith("YES")
        except Exception as e:
            log.warning(f"is_homework_image failed, default NO: {e}")
            return False

    def grade_homework(self, image_paths: list[Path], transcript: str | None = None) -> str:
        from ..prompts import grader

        prompt = grader.build_prompt(transcript=transcript)
        system = grader.SYSTEM_PROMPT
        return self.grade_images(image_paths, prompt, system=system)


def build_aliyun_vl_client() -> OpenAIVLClient:
    """Construct an Aliyun Bailian VL client from settings."""
    s = get_settings()
    cfg = s.model("vision") or {}
    return OpenAIVLClient(
        base_url=s.aliyun_base_url,
        api_key=s.aliyun_api_key,
        model=cfg.get("name", "qwen-vl-plus"),
        temperature=cfg.get("temperature", 0.4),
        max_tokens=cfg.get("max_tokens", 1024),
    )


def build_volcano_vl_client() -> OpenAIVLClient:
    """Construct a Volcano Ark VL client from settings."""
    s = get_settings()
    cfg = s.model("vision") or {}
    return OpenAIVLClient(
        base_url=s.volc_base_url,
        api_key=s.volc_api_key,
        model=cfg.get("name", "doubao-1-5-vision-pro-32k"),
        temperature=cfg.get("temperature", 0.4),
        max_tokens=cfg.get("max_tokens", 1024),
    )
