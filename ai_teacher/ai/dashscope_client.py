"""Qwen-VL multimodal client (DashScope).

We always send images as base64 data URLs to avoid needing a public file host.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Iterable

import dashscope
from dashscope import MultiModalConversation

from ..utils.config import get_settings
from ..utils.logger import get_logger
from ..utils.retry import with_retry

log = get_logger()


def _file_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(suffix, "jpeg")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


class QwenVLClient:
    def __init__(self) -> None:
        s = get_settings()
        dashscope.api_key = s.dashscope_api_key
        self.cfg = s.model("vision") or {}
        self.model = self.cfg.get("name", "qwen2.5-vl-72b-instruct")

    @with_retry(max_attempts=3, backoff=2.0, initial_delay=1.0)
    def grade_images(
        self,
        image_paths: Iterable[Path],
        prompt: str,
        *,
        system: str | None = None,
    ) -> str:
        """Ask Qwen-VL to grade a set of images with the given prompt."""
        content: list[dict] = []
        for p in image_paths:
            content.append({"image": _file_to_data_url(p)})
        content.append({"text": prompt})

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": [{"text": system}]})
        messages.append({"role": "user", "content": content})

        log.debug(f"calling Qwen-VL model={self.model} images={len(image_paths)-1}")
        resp = MultiModalConversation.call(
            model=self.model,
            messages=messages,
            temperature=self.cfg.get("temperature", 0.4),
            max_tokens=self.cfg.get("max_tokens", 1024),
            vl_high_resolution_images=self.cfg.get("high_resolution", True),
        )
        if getattr(resp, "status_code", 200) != 200:
            raise RuntimeError(
                f"Qwen-VL error: {getattr(resp, 'code', '?')} {getattr(resp, 'message', '?')}"
            )
        out = resp.output.choices[0].message.content
        if isinstance(out, list):
            return "".join(part.get("text", "") for part in out if isinstance(part, dict))
        return str(out)

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
        """Generate a structured Chinese grading report."""
        from ..prompts import grader

        prompt = grader.build_prompt(transcript=transcript)
        system = grader.SYSTEM_PROMPT
        return self.grade_images(image_paths, prompt, system=system)
