"""Volcano Engine Ark — Doubao multimodal client.

Volcano Engine exposes its Doubao vision models through an OpenAI-compatible
endpoint. We reuse the `openai` SDK and pass images as base64 data URLs.

Prerequisites (one-time setup in the Volcano console):
  1. Open "方舟 / Ark" service
  2. Create an API Key
  3. In "在线推理", create an endpoint for a vision model, e.g.
       doubao-1-5-vision-pro-32k
     and copy the model id (looks like "ep-xxxxxx" or the model name)
  4. Put the API key in .env as VOLC_API_KEY
  5. Put the model id in config.yaml under models.vision.name
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


class DoubaoVLClient:
    """OpenAI-compatible Doubao vision client via Volcano Ark."""

    def __init__(self) -> None:
        s = get_settings()
        api_key = s.volc_api_key
        if not api_key:
            raise RuntimeError("VOLC_API_KEY not set in .env")
        self.client = OpenAI(
            api_key=api_key,
            base_url=s.volc_base_url,
        )
        self.cfg = s.model("vision") or {}
        self.model = self.cfg.get("name") or "doubao-1-5-vision-pro-32k"

    @with_retry(max_attempts=3, backoff=2.0, initial_delay=1.0)
    def grade_images(
        self,
        image_paths: Iterable[Path],
        prompt: str,
        *,
        system: str | None = None,
    ) -> str:
        """Ask Doubao vision to grade a set of images with the given prompt."""
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

        log.debug(f"calling Doubao VL model={self.model} images={len(image_paths)-1}")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.cfg.get("temperature", 0.4),
            max_tokens=self.cfg.get("max_tokens", 1024),
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
