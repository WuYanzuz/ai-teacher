"""Message dispatcher — the heart of the bot.

Routes incoming WeChat messages to the right pipeline based on:
  - Whether it's a group we're listening to
  - Whether it's a media type we care about
  - Whether we're in quiet hours / over rate limit
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .ai.classifier import HomeworkClassifier
from .ai.deepseek_client import TextClient as DeepSeekClient
from .ai.paraformer_client import ParaformerClient
from .ai.vision_router import get_vision_client
from .child_id.resolver import ChildIdResolver
from .media import audio as audio_mod
from .media import video as video_mod
from .media.image import compress_image
from .prompts import growth as growth_prompts
from .storage import db as storage_db
from .storage.models import Child
from .teacher.notifier import TeacherNotifier
from .utils.config import get_settings
from .utils.helpers import safe_filename
from .utils.logger import get_logger
from .utils.ratelimit import QuietHours, RateLimiter, human_delay
from .wcf_client import (
    MSG_TYPE_IMAGE,
    MSG_TYPE_VIDEO,
    MSG_TYPE_VOICE,
    WeChatMsg,
    WcfClient,
)

if TYPE_CHECKING:
    pass

log = get_logger()


class Dispatcher:
    def __init__(self, wcf: WcfClient) -> None:
        self.wcf = wcf
        self.settings = get_settings()
        self.resolver = ChildIdResolver()
        self.limiter = RateLimiter()
        self.quiet = QuietHours(self.settings.quiet_hour_start, self.settings.quiet_hour_end)
        self.classifier = HomeworkClassifier()
        self.vl = get_vision_client()
        # ASR is optional — if DashScope key is missing, voice-only homework is skipped
        if self.settings.dashscope_api_key:
            self.asr = ParaformerClient()
        else:
            self.asr = None
            log.warning("DASHSCOPE_API_KEY 未设置,语音作业将被跳过 (只处理图片/视频)")
        self.text = DeepSeekClient()
        self.notifier = TeacherNotifier(wcf)
        # Ensure DB is ready
        storage_db.init_db()
        # Concurrency guard: process messages serially to keep API call rate low
        self._queue_lock = threading.Lock()

    # --------- public entry ---------

    def handle(self, msg: WeChatMsg) -> None:
        """Process a single incoming message."""
        try:
            self._handle_locked(msg)
        except Exception:
            log.exception("handle() crashed for msg_id=%s", msg.id)

    def _handle_locked(self, msg: WeChatMsg) -> None:
        # 1) Group filter
        if not self.wcf.in_whitelist(msg.roomid):
            return
        # 2) Skip self
        if self.wcf.is_self(msg.sender):
            return

        # 3) Teacher private-chat commands (1-on-1 to our own account)
        if not msg.is_group and msg.sender == self.settings.teacher_wxid:
            self._handle_teacher_command(msg)
            return

        # 4) Only media in groups
        if not msg.is_group:
            return
        if msg.type not in (MSG_TYPE_IMAGE, MSG_TYPE_VOICE, MSG_TYPE_VIDEO):
            return

        # 5) Quiet hours
        if self.quiet.is_quiet():
            log.debug(f"quiet hour, skip msg_id={msg.id}")
            return

        # 6) Rate limit
        allowed, reason = self.limiter.allow(msg.sender)
        if not allowed:
            log.info(f"rate-limited: {reason}, sender={msg.sender}")
            return

        # 7) Process in a worker thread so we don't block wcferry's message thread
        threading.Thread(
            target=self._process_media, args=(msg,), daemon=True
        ).start()

    # --------- media pipeline ---------

    def _process_media(self, msg: WeChatMsg) -> None:
        with self._queue_lock:
            self.limiter.consume(msg.sender)
            try:
                if msg.type == MSG_TYPE_IMAGE:
                    self._pipeline_image(msg)
                elif msg.type == MSG_TYPE_VOICE:
                    self._pipeline_voice(msg)
                elif msg.type == MSG_TYPE_VIDEO:
                    self._pipeline_video(msg)
            except Exception:
                log.exception("media pipeline failed")
                self.notifier.send_skipped(reason="处理异常,已记录日志", sender=msg.sender)

    def _pipeline_image(self, msg: WeChatMsg) -> None:
        path = Path(msg.content)
        if not path.exists():
            log.warning(f"image path missing: {path}")
            return
        if not self.classifier.quick_filter(
            msg_type=msg.type, file_size_bytes=path.stat().st_size, sender_wxid=msg.sender
        ):
            return
        compressed = compress_image(path) if path.suffix.lower() != ".jpg" else path
        transcript = None  # no audio for image messages
        is_hw = self.classifier.looks_like_homework(compressed, transcript=transcript)
        if not is_hw:
            log.info(f"msg_id={msg.id} classified as non-homework, skip")
            return
        feedback = self.vl.grade_homework([compressed], transcript=transcript)
        self._finalize(msg, media_type="image", media_path=str(compressed),
                       transcript=transcript, feedback=feedback)

    def _pipeline_voice(self, msg: WeChatMsg) -> None:
        if self.asr is None:
            log.info(f"msg_id={msg.id} 跳过语音作业 (ASR 未配置)")
            return
        silk = self.wcf.download_voice(msg.id, self.settings.cache_dir)
        if not silk:
            log.warning(f"download_voice failed for msg_id={msg.id}")
            return
        wav = audio_mod.silk_to_wav(silk)
        transcript = self.asr.transcribe_file(wav)
        if not transcript:
            log.info(f"msg_id={msg.id} empty transcript, skip")
            return
        # For pure voice, we still want a visual grade. Synthesize a
        # "transcript-only" frame by writing the transcript into a 1x1 PNG
        # (cheap) and pass it to VL with the transcript context.
        # Simpler: just use the text + DeepSeek to score pronunciation/fluency.
        feedback = self._grade_audio_homework(transcript)
        self._finalize(msg, media_type="voice", media_path=str(wav),
                       transcript=transcript, feedback=feedback)

    def _pipeline_video(self, msg: WeChatMsg) -> None:
        path = Path(msg.content)
        if not path.exists():
            log.warning(f"video path missing: {path}")
            return
        if not self.classifier.quick_filter(
            msg_type=msg.type, file_size_bytes=path.stat().st_size, sender_wxid=msg.sender
        ):
            return
        out_dir = self.settings.cache_dir / f"frames_{safe_filename(path.stem)}"
        frames = video_mod.extract_frames(path, out_dir)
        if not frames:
            return
        # Extract audio from video too, if present
        transcript = None
        if self.asr is not None:
            try:
                from .media.ffmpeg_utils import require_ffmpeg
                import subprocess

                audio_out = out_dir / "audio.wav"
                subprocess.run(
                    [require_ffmpeg(), "-y", "-i", str(path), "-ar", "16000", "-ac", "1", str(audio_out)],
                    check=False, capture_output=True,
                )
                if audio_out.exists() and audio_out.stat().st_size > 1024:
                    transcript = self.asr.transcribe_file(audio_out)
            except Exception:
                log.debug("no audio track in video, ok")

        is_hw = self.classifier.looks_like_homework(frames[0], transcript=transcript)
        if not is_hw:
            log.info(f"msg_id={msg.id} video classified as non-homework, skip")
            return
        feedback = self.vl.grade_homework(frames, transcript=transcript)
        self._finalize(msg, media_type="video", media_path=str(path),
                       transcript=transcript, feedback=feedback)

    def _grade_audio_homework(self, transcript: str) -> str:
        """Score a voice-only homework using DeepSeek (no visual)."""
        system = (
            "你是一名幼儿/小学低年级老师,正在点评孩子的朗读或口头作业。"
            "根据转写出的文字,从清晰度、流畅度、完整度三个维度给点评,"
            "并给出 1-2 句鼓励。不超过 100 字。"
        )
        user = f"转写文本: <<{transcript}>>\n\n请按'亮点/建议/鼓励'三段输出。"
        return self.text.chat(system, user, temperature=0.5)

    # --------- finalize ---------

    def _finalize(
        self,
        msg: WeChatMsg,
        *,
        media_type: str,
        media_path: str | None,
        transcript: str | None,
        feedback: str,
    ) -> None:
        import time
        from .teacher.commands import push_recent

        # Resolve child. group_nickname isn't on WeChatMsg for media, so the
        # resolver falls back to its hash-based default if no binding.
        guess = self.resolver.resolve(msg.sender, group_nickname=None)
        if guess.source == "hash":
            self.notifier.send_ask_child_name(
                parent_nick=None, parent_wxid=msg.sender, media_type=media_type
            )
        child = storage_db.upsert_child(
            name=guess.name,
            parent_wxid=msg.sender,
            group_nick=guess.source if guess.source == "nickname" else None,
        )
        # Look up last feedback for context (only if different from current)
        last = (
            storage_db.Homework.select()
            .where(storage_db.Homework.child == child, storage_db.Homework.is_homework == 1)
            .order_by(storage_db.Homework.created_at.desc())
            .first()
        )
        last_feedback = last.feedback if (last and last.feedback and last.feedback != feedback) else None
        # Persist
        hw = storage_db.record_homework(
            child=child,
            group_roomid=msg.roomid,
            msg_id=msg.id,
            media_type=media_type,
            media_path=media_path,
            transcript=transcript,
            is_homework=True,
            feedback=feedback,
        )
        if hw is None:
            log.info(f"duplicate msg_id={msg.id}, skip")
            return
        # Track for teacher ack/ignore/revert commands
        push_recent({
            "parent_wxid": msg.sender,
            "child_name": child.name,
            "homework_id": hw.id,
            "msg_id": msg.id,
            "ts": time.time(),
        })
        # Send to teacher
        self.notifier.send_homework_feedback(
            child_name=child.name,
            parent_nick=child.group_nick_pattern,
            media_type=media_type,
            feedback=feedback,
            transcript=transcript,
            last_feedback=last_feedback,
        )

    def _trend_hint(self, child: Child, current_feedback: str) -> str | None:
        from peewee import fn

        prev = (
            storage_db.Homework.select()
            .where(storage_db.Homework.child == child, storage_db.Homework.is_homework == 1)
            .order_by(storage_db.Homework.created_at.desc())
            .offset(1)
            .limit(1)
            .first()
        )
        if not prev or not prev.feedback:
            return "首次记录,无对比"
        # Very rough heuristic: if both have a "建议" segment, compare length
        return "见历史记录"

    # --------- teacher private commands ---------

    def _handle_teacher_command(self, msg: WeChatMsg) -> None:
        from .teacher.commands import HELP_TEXT, parse_command, pop_recent

        cmd = parse_command(msg.content or "")
        if not cmd:
            return
        action = cmd.get("action")
        if action == "register":
            self.resolver.register(cmd["wxid"], cmd["name"])
            self.notifier.send_register_confirmation(cmd["name"], cmd["wxid"], None)
        elif action == "bind_nick":
            # bind a group nickname pattern to a child name
            child = storage_db.Child.select().where(storage_db.Child.name == cmd["name"]).first()
            if child:
                child.group_nick_pattern = cmd["pattern"]
                child.save()
            self.notifier.send_register_confirmation(cmd["name"], "(by group nick)", cmd["pattern"])
        elif action == "unregister":
            self.resolver.unregister(cmd["wxid"])
            self.wcf.send_text(f"已解绑 {cmd['wxid']}", self.settings.teacher_wxid)
        elif action == "report":
            name = cmd["name"]
            child = storage_db.Child.select().where(storage_db.Child.name == name).first()
            if not child:
                self.wcf.send_text(f"未找到孩子: {name}", self.settings.teacher_wxid)
                return
            history = storage_db.child_history(child, limit=10)
            prompt = growth_prompts.build_report_prompt(name, history)
            report = self.text.chat("你是一名幼儿老师,正在为家长准备孩子的成长小结。", prompt, temperature=0.5)
            self.notifier.send_growth_report(name, report)
        elif action == "ack":
            entry = pop_recent()
            if not entry:
                self.wcf.send_text("最近没有可确认的作业", self.settings.teacher_wxid)
            else:
                self.resolver.register(entry["parent_wxid"], entry["child_name"])
                self.wcf.send_text(
                    f"✓ 已确认: {entry['child_name']} (家长 {entry['parent_wxid']})",
                    self.settings.teacher_wxid,
                )
        elif action == "ignore":
            entry = pop_recent()
            if not entry:
                self.wcf.send_text("最近没有可忽略的作业", self.settings.teacher_wxid)
            else:
                from .storage.models import Homework
                Homework.update(is_homework=0).where(
                    Homework.id == entry["homework_id"]
                ).execute()
                self.notifier.send_ignored_ack()
        elif action == "revert":
            entry = pop_recent()
            if not entry:
                self.wcf.send_text("最近没有可撤销的记录", self.settings.teacher_wxid)
            else:
                from .storage.models import Homework
                Homework.delete().where(Homework.id == entry["homework_id"]).execute()
                self.notifier.send_revert_ack()
        elif action == "rename":
            entry = pop_recent()
            if not entry:
                self.wcf.send_text("最近没有可改名的作业", self.settings.teacher_wxid)
            else:
                new_name = cmd["name"]
                old_name = entry["child_name"]
                self.resolver.register(entry["parent_wxid"], new_name)
                from .storage.models import Child
                child = Child.select().where(Child.name == old_name).first()
                if child:
                    child.name = new_name
                    child.save()
                self.notifier.send_rename_confirmation(new_name, entry["parent_wxid"])
        elif action == "help":
            self.wcf.send_text(HELP_TEXT, self.settings.teacher_wxid)
        elif action == "cleanup":
            n = storage_db.cleanup_old_cache(self.settings.cache_dir, self.settings.cache_retention_days)
            self.wcf.send_text(f"已清理 {n} 个过期文件", self.settings.teacher_wxid)
