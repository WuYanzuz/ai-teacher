"""WeChatFerry (wcferry) client wrapper.

Goals:
- Single import point so the rest of the code can be unit-tested without a
  real WeChat client.
- Always remember: this layer talks to a non-official, hook-based protocol.
  Every method here corresponds to a wcferry SDK call, and the account can
  be banned if abused.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .utils.config import get_settings
from .utils.logger import get_logger

log = get_logger()


@dataclass
class WeChatMsg:
    """Normalized message representation.

    We don't reuse wcferry.WxMsg directly so that tests can construct messages
    without the SDK being installed.
    """

    id: int
    type: int  # 1=text 3=image 34=voice 43=video 47=emoji 49=file 10000=system
    is_group: bool
    roomid: str  # group wxid
    sender: str  # sender wxid (in group) or the contact wxid (1-on-1)
    content: str  # text, or local file path for media, or xml for system
    raw: object = None  # original SDK object if available


# Message type constants (mirrors wcferry)
MSG_TYPE_TEXT = 1
MSG_TYPE_IMAGE = 3
MSG_TYPE_VOICE = 34
MSG_TYPE_VIDEO = 43
MSG_TYPE_EMOJI = 47
MSG_TYPE_FILE = 49
MSG_TYPE_SYSTEM = 10000


class WcfClient:
    """Thin wrapper over the wcferry SDK.

    The class is constructed lazily: the underlying SDK may not be installed
    on dev machines. Code that does not call `start()` works fine for tests.
    """

    def __init__(self) -> None:
        self._wcf = None
        self._lock = threading.Lock()
        self._started = False
        self._self_wxid: str = ""

    # ----- lifecycle -----

    def start(self) -> None:
        """Inject into the running PC WeChat and start receiving messages."""
        if self._started:
            return
        from wcferry import Wcf  # local import so tests don't need the SDK

        log.info("Injecting wcferry into PC WeChat ...")
        self._wcf = Wcf()
        self._self_wxid = self._wcf.self_wxid
        self._wcf.enable_receiving_msg()
        self._started = True
        log.info(f"Wcf ready, self_wxid={self._self_wxid}")

    def stop(self) -> None:
        if not self._started:
            return
        try:
            self._wcf.disable_receiving_msg()
        except Exception as e:  # pragma: no cover
            log.warning(f"disable_receiving_msg error: {e}")
        self._started = False

    @property
    def self_wxid(self) -> str:
        return self._self_wxid

    @property
    def started(self) -> bool:
        return self._started

    # ----- message handlers -----

    def on_message(self, handler: Callable[[WeChatMsg], None]) -> None:
        """Register a single message handler.

        The handler runs on wcferry's internal thread, so it should not block.
        """
        if self._wcf is None:
            raise RuntimeError("WcfClient.start() must be called first")

        def _adapter(raw_msg):  # type: ignore[no-untyped-def]
            try:
                msg = self._normalize(raw_msg)
                handler(msg)
            except Exception:
                log.exception("message handler crashed")

        self._wcf.add_msg_handler(_adapter)

    def keep_running(self) -> None:
        """Block forever (wcferry's main loop)."""
        if self._wcf is None:
            raise RuntimeError("WcfClient.start() must be called first")
        self._wcf.keep_running()

    # ----- send -----

    def send_text(self, text: str, receiver: str, at_list: Optional[list[str]] = None) -> None:
        """Send a text message to a contact or group."""
        if self._wcf is None:
            log.warning(f"[stub] send_text -> {receiver}: {text[:50]}")
            return
        with self._lock:
            self._wcf.send_text(text, receiver, at_list=at_list or [])

    def send_image(self, path: str | Path, receiver: str) -> None:
        if self._wcf is None:
            log.warning(f"[stub] send_image -> {receiver}: {path}")
            return
        with self._lock:
            self._wcf.send_image(str(path), receiver)

    # ----- media download -----

    def download_voice(self, msg_id: int, out_dir: str | Path, timeout: int = 10) -> Optional[Path]:
        """Download a voice (.silk) file. Returns the local path or None."""
        if self._wcf is None:
            log.warning(f"[stub] download_voice for msg_id={msg_id}")
            return None
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            p = self._wcf.get_audio_msg(msg_id, str(out_dir), timeout=timeout)
            return Path(p) if p else None
        except Exception as e:
            log.exception(f"download_voice failed: {e}")
            return None

    def get_voice_buf(self, msg_id: int, timeout: int = 10) -> Optional[bytes]:
        """Return the raw .silk bytes (in memory) for the given message id."""
        if self._wcf is None:
            return None
        try:
            return self._wcf.get_audio_msg_buf(msg_id, timeout=timeout)
        except Exception as e:  # pragma: no cover - depends on wcferry version
            log.exception(f"get_voice_buf failed: {e}")
            return None

    # ----- bookkeeping -----

    def is_self(self, wxid: str) -> bool:
        return wxid == self._self_wxid

    def in_whitelist(self, roomid: str) -> bool:
        return roomid in get_settings().whitelist_groups

    # ----- internal -----

    def _normalize(self, raw) -> WeChatMsg:  # type: ignore[no-untyped-def]
        """Map a wcferry.WxMsg to our internal dataclass."""
        return WeChatMsg(
            id=raw.id,
            type=raw.type,
            is_group=bool(raw.is_group),
            roomid=raw.roomid,
            sender=raw.sender,
            content=raw.content,
            raw=raw,
        )
