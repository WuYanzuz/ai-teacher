"""Send notifications to the designated teacher via private chat."""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

from ..utils.config import get_settings
from ..utils.logger import get_logger
from ..utils.ratelimit import human_delay

if TYPE_CHECKING:
    from ..wcf_client import WcfClient

log = get_logger()


class TeacherNotifier:
    def __init__(self, wcf: "WcfClient") -> None:
        self.wcf = wcf
        self.teacher_wxid = get_settings().teacher_wxid

    def _send(self, text: str) -> None:
        if not self.teacher_wxid:
            log.warning("teacher_wxid not configured; skipping notification")
            return
        time.sleep(human_delay(2, 6))
        self.wcf.send_text(text, self.teacher_wxid)

    def send_homework_feedback(
        self,
        *,
        child_name: str,
        media_type: str,
        feedback: str,
        transcript: str | None = None,
        trend: str | None = None,
    ) -> None:
        parts: list[str] = []
        parts.append(f"【新作业】{datetime.now().strftime('%m-%d %H:%M')}")
        parts.append(f"小朋友: {child_name}")
        parts.append(f"类型: {self._type_label(media_type)}")
        if transcript:
            t = transcript[:80] + "..." if len(transcript) > 80 else transcript
            parts.append(f"语音转写: {t}")
        parts.append("---")
        parts.append(feedback.strip())
        if trend:
            parts.append("---")
            parts.append(f"对比上次: {trend}")
        text = "\n".join(parts)
        log.info(f"sending feedback to teacher for {child_name}")
        self._send(text)

    def send_skipped(self, *, reason: str, sender: str) -> None:
        text = f"【跳过】{sender}: {reason}"
        log.info(text)
        self._send(text)

    def send_register_confirmation(self, child_name: str, parent_wxid: str) -> None:
        self._send(f"已为家长 {parent_wxid} 绑定孩子: {child_name}")

    def send_growth_report(self, child_name: str, report: str) -> None:
        text = f"【成长小结】{child_name}\n\n{report}"
        self._send(text)

    @staticmethod
    def _type_label(t: str) -> str:
        return {"image": "图片", "voice": "语音", "video": "视频"}.get(t, t)
