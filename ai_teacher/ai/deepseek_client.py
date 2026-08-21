"""Text LLM client. Supports multiple providers, all OpenAI-compatible.

Choose via config.yaml -> models.text.provider:
  - "aliyun"  : Aliyun Bailian (qwen-plus, deepseek-v3, etc.)
  - "ark"     : Volcano Ark Plan endpoint
  - "deepseek": DeepSeek official
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
        provider = cfg.get("provider", "aliyun").lower()

        if provider == "aliyun":
            if not s.aliyun_api_key:
                raise RuntimeError("ALIYUN_API_KEY not set in .env")
            self.client = OpenAI(api_key=s.aliyun_api_key, base_url=s.aliyun_base_url)
            log.info(f"text provider: Aliyun Bailian ({s.aliyun_base_url[:50]}...)")
        elif provider == "ark":
            if not s.volc_api_key:
                raise RuntimeError("VOLC_API_KEY not set in .env")
            self.client = OpenAI(api_key=s.volc_api_key, base_url=s.volc_base_url)
            log.info(f"text provider: Volcano Ark ({s.volc_base_url[:50]}...)")
        else:  # deepseek official
            if not s.deepseek_api_key:
                raise RuntimeError("DEEPSEEK_API_KEY not set in .env")
            self.client = OpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url)
            log.info(f"text provider: DeepSeek official")

        self.cfg = cfg
        self.model = cfg.get("name", "qwen-plus")

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

    def polish(self, raw_feedback: str, *, style: str = "俏皮") -> str:
        system = (
            "你是一位超有爱的幼儿老师姐姐,负责把初步的作业点评润色成发给家长看的微信消息。"
            "要求:\n"
            "  1. 语气俏皮可爱,像同龄的姐姐/哥哥在夸小朋友,要有网感"
            "  2. 可以用 emoji,但最多 2-3 个,不要堆砌"
            "  3. 可以用叠词、儿歌、小动物/小道具的比喻(比如'小超人'、'小火车'、'小火箭')"
            "  4. 短句为主,有节奏感,像在跟家长聊天"
            "  5. 不超过 100 字,不出现孩子姓名/学校等隐私信息"
            "  6. 保持原文核心评价,不要瞎编具体错误"
            ""
            "示例风格(从'温柔'升级到'俏皮'):\n"
            "  温柔: 孩子很认真,字迹工整,继续保持。\n"
            "  俏皮: 哇哦~小宝贝今天的字写得超工整,小火车都开过去啦🚂,继续冲冲冲!"
        )
        user = (
            f"请把下面的初评润色成{style}风格的微信消息,"
            f"保持核心信息但更有网感、更可爱。直接输出润色后的文本,不要解释,不要前缀。\n\n"
            f"---初评---\n{raw_feedback}"
        )
        return self.chat(system, user, temperature=0.85)


# Backwards-compat alias
DeepSeekClient = TextClient
