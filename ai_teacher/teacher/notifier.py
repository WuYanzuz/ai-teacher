"""Send notifications to the designated teacher via private chat.

Message format (v2, scannable + actionable):

  🌟 新作业 | 小明（来自：小明爸）
  🕐 08-21 11:33  📷 图片
  📝 类型: 看图说话
  👀 上次: 流利度很好, 表情生动
  💬 本次点评:
  <polished feedback>
  ────────────────────
  回复: 对/✓ | 这是 XX | 忽略/× | 撤销
"""

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


def _media_emoji(t: str) -> str:
    return {"image": "📷", "voice": "🎤", "video": "🎬"}.get(t, "📄")


def _media_label(t: str) -> str:
    return {"image": "图片", "voice": "语音", "video": "视频"}.get(t, t)


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
        parent_nick: str | None,
        media_type: str,
        feedback: str,
        transcript: str | None = None,
        last_feedback: str | None = None,
    ) -> None:
        """Send a structured, scannable feedback message to the teacher."""
        parts: list[str] = []
        # Header
        parent_part = f"（来自：{parent_nick}）" if parent_nick else ""
        parts.append(f"🌟 新作业 | {child_name} {parent_part}".strip())
        # Meta line
        meta = f"🕐 {datetime.now().strftime('%m-%d %H:%M')}  {_media_emoji(media_type)} {_media_label(media_type)}"
        parts.append(meta)
        # Last feedback context
        if last_feedback:
            short = last_feedback[:50] + ("..." if len(last_feedback) > 50 else "")
            parts.append(f"👀 上次: {short}")
        # This feedback
        parts.append("💬 本次点评:")
        parts.append(feedback.strip())
        # Transcript if any
        if transcript:
            t = transcript[:80] + "..." if len(transcript) > 80 else transcript
            parts.append(f"")
            parts.append(f"🎙️ 语音: {t}")
        # Action hint
        parts.append("────────────────────────")
        parts.append("回复: ✓对  |  这是 XX  |  ×忽略  |  撤销")

        text = "\n".join(parts)
        log.info(f"sending feedback to teacher for {child_name}")
        self._send(text)

    def send_ask_child_name(self, *, parent_nick: str | None, parent_wxid: str, media_type: str) -> None:
        """Ask the teacher who this anonymous parent is."""
        parts = [
            "❓ 不知道这是谁的孩子",
            f"群昵称: {parent_nick or '(无)'}",
            f"wxid: {parent_wxid}",
            f"类型: {_media_label(media_type)}",
            "",
            "请回复 \"这是 XX\" 告诉我孩子名",
            "(机器人会记住, 下次自动识别)",
        ]
        self._send("\n".join(parts))

    def send_skipped(self, *, reason: str, sender: str) -> None:
        text = f"⏭️ 跳过 {sender}: {reason}"
        log.info(text)
        self._send(text)

    def send_register_confirmation(self, child_name: str, parent_wxid: str, parent_nick: str | None = None) -> None:
        nick_part = f" (群昵称: {parent_nick})" if parent_nick else ""
        self._send(f"✅ 已绑定\n家长: {parent_wxid}{nick_part}\n→ 孩子: {child_name}")

    def send_rename_confirmation(self, child_name: str, parent_wxid: str) -> None:
        self._send(f"🔁 已更正为: {child_name} (家长 {parent_wxid})")

    def send_growth_report(self, child_name: str, report: str) -> None:
        text = f"📈 【成长小结】{child_name}\n\n{report}"
        self._send(text)

    def send_ignored_ack(self) -> None:
        self._send("✅ 已忽略这条 (标记为非作业)")

    def send_revert_ack(self) -> None:
        self._send("↩️ 已撤销上次的记录")
