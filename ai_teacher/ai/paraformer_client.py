"""Paraformer-v2 ASR client (DashScope)."""

from __future__ import annotations

from pathlib import Path

import dashscope
from dashscope.audio.asr import Recognition

from ..utils.config import get_settings
from ..utils.logger import get_logger
from ..utils.retry import with_retry

log = get_logger()


class ParaformerClient:
    def __init__(self) -> None:
        s = get_settings()
        dashscope.api_key = s.dashscope_api_key
        self.cfg = s.model("asr") or {}

    @with_retry(max_attempts=3, backoff=2.0, initial_delay=1.0)
    def transcribe_file(self, wav_path: Path) -> str:
        if not wav_path.exists():
            raise FileNotFoundError(wav_path)

        log.debug(f"transcribing {wav_path.name} ({wav_path.stat().st_size//1024}KB)")
        rec = Recognition(
            model=self.cfg.get("name", "paraformer-v2"),
            format="wav",
            sample_rate=self.cfg.get("sample_rate", 16000),
            language_hints=["zh", "en"],
            callback=None,
        )
        result = rec.call(str(wav_path))
        # result is a RecognitionResult; .get_sentence() returns list of {text, ...}
        try:
            sentences = result.get_sentence() or []
        except Exception:
            sentences = []
        text = "".join((s.get("text", "") if isinstance(s, dict) else str(s)) for s in sentences)
        log.info(f"transcribed {wav_path.name}: {len(text)} chars")
        return text.strip()
