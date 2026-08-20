"""Text LLM client. Supports both DeepSeek official and Volcano Ark (Doubao Ark).

Both providers speak the OpenAI protocol, so we wrap the `openai` SDK.
Choose via config.yaml -> models.text.provider:
  - "deepseek" -> use DEEPSEEK_API_KEY + DEEPSEEK_BASE_URL
  - "ark"      -> use VOLC_API_KEY + volc_base_url
"""

from __future__ import annotations

from openai import OpenAI

from ..utils.config import get_settings
from ..utils.logger import get_logger
from ..utils.retry import with_retry

log = get_logger()


class TextClient:
    def __init__(self) -> None:
        s = get_settings()
        cfg = s.model("text") or {}
        provider = cfg.get("provider", "deepseek").lower()

        if provider == "ark":
            if not s.volc_api_key:
                raise RuntimeError("VOLC_API_KEY not set in .env")
            self.client = OpenAI(api_key=s.volc_api_key, base_url=s.volc_base_url)
            log.info("text provider: Volcano Ark (Doubao)")
        else:
            if not s.deepseek_api_key:
                raise RuntimeError("DEEPSEEK_API_KEY not set in .env")
            self.client = OpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url)
            log.info("text provider: DeepSeek official")

        self.cfg = cfg
        self.model = cfg.get("name", "deepseek-chat")

    @with_retry(max_attempts=3, backoff=2.0, initial_delay=1.0)
    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        log.debug(f"text chat model={self.model}, prompt~{len(user)} chars")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature or self.cfg.get("temperature", 0.6),
            max_tokens=max_tokens or self.cfg.get("max_tokens", 1024),
        )
        return resp.choices[0].message.content or ""

    def polish(self, raw_feedback: str, *, style: str = "温柔") -> str:
        system = (
            "你是一名温柔的幼儿老师助手,负责把初步的作业点评润色成发给家长看的版本。"
            "要求:语气温暖、具体、不超过 100 字、不出现孩子姓名/学校等隐私信息。"
        )
        user = (
            f"请把下面的初评改写成更口语化、{style}的风格,"
            f"保持核心信息但更有人情味。直接输出润色后的文本,不要解释。\n\n"
            f"---初评---\n{raw_feedback}"
        )
        return self.chat(system, user, temperature=0.7)


# Backwards-compat alias
DeepSeekClient = TextClient
