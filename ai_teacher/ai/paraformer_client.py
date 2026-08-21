"""Paraformer file transcription client (DashScope).

Flow:
  1. Upload local wav to OSS, get a 1h signed URL
  2. Call Transcription.async_call(paraformer-v2, file_urls=[url])
  3. Poll for completion
  4. Download the transcription_url JSON, extract text + sentence timestamps
  5. Delete OSS object

Pricing: paraformer-v2 (file) ~¥0.0001/秒  (vs realtime-v1 ~¥0.00024/秒)
"""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path

import dashscope
import requests
from dashscope.audio.asr import Transcription

from ..media.oss_uploader import OSSUploader
from ..utils.config import get_settings
from ..utils.logger import get_logger
from ..utils.retry import with_retry

log = get_logger()


class TranscriptionResult:
    """Normalized transcription output."""

    def __init__(self, text: str, sentences: list[dict], duration_ms: int) -> None:
        self.text = text
        self.sentences = sentences
        self.duration_ms = duration_ms

    def __str__(self) -> str:
        return self.text


class ParaformerClient:
    def __init__(self) -> None:
        s = get_settings()
        dashscope.api_key = s.dashscope_api_key
        self.cfg = s.model("asr") or {}
        self.model = self.cfg.get("name", "paraformer-v2")
        self._oss: OSSUploader | None = None

    def _get_oss(self) -> OSSUploader:
        if self._oss is None:
            self._oss = OSSUploader()
        return self._oss

    def _download_result_json(self, url: str) -> dict:
        log.debug(f"downloading transcription result JSON")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.json()

    def _parse_result(self, result) -> TranscriptionResult:
        """Extract text + sentences from a Transcription.wait() result."""
        # The result has nested structure: result.output.results[].transcription_url
        out = result.output
        results = out.get("results", []) or []
        for r in results:
            if r.get("subtask_status") != "SUCCEEDED":
                continue
            turl = r.get("transcription_url")
            if not turl:
                continue
            data = self._download_result_json(turl)
            transcripts = data.get("transcripts", []) or []
            if not transcripts:
                continue
            t0 = transcripts[0]
            text = t0.get("text", "").strip()
            sentences = t0.get("sentences", []) or []
            duration = t0.get("content_duration_in_milliseconds", 0)
            return TranscriptionResult(text=text, sentences=sentences, duration_ms=duration)
        raise RuntimeError(f"no successful transcription in result: {out}")

    def _transcribe_url(self, url: str) -> TranscriptionResult:
        log.debug(f"submitting transcription task for {self.model}: {url[:80]}...")
        task = Transcription.async_call(
            model=self.model,
            file_urls=[url],
            language_hints=["zh", "en"],
        )
        if task.status_code != HTTPStatus.OK:
            raise RuntimeError(f"async_call failed: {task.code} {task.message}")
        log.debug(f"task_id={task.output.task_id}, waiting ...")
        result = Transcription.wait(task=task.output.task_id, timeout=120)
        if result.status_code != HTTPStatus.OK:
            raise RuntimeError(
                f"transcription failed: {result.output.get('message', '?')}"
            )
        return self._parse_result(result)

    @with_retry(max_attempts=2, backoff=2.0, initial_delay=1.0)
    def transcribe_file(self, wav_path: Path) -> str:
        if not wav_path.exists():
            raise FileNotFoundError(wav_path)

        oss = self._get_oss()
        url, key = oss.upload_audio(wav_path, expire_sec=3600)
        try:
            res = self._transcribe_url(url)
        finally:
            oss.delete(key)

        log.info(
            f"transcribed {wav_path.name}: {len(res.text)} chars, "
            f"{res.duration_ms}ms, {len(res.sentences)} sentences"
        )
        return res.text

    def transcribe_file_full(self, wav_path: Path) -> TranscriptionResult:
        """Like transcribe_file but returns full result with sentence timestamps."""
        if not wav_path.exists():
            raise FileNotFoundError(wav_path)
        oss = self._get_oss()
        url, key = oss.upload_audio(wav_path, expire_sec=3600)
        try:
            return self._transcribe_url(url)
        finally:
            oss.delete(key)
