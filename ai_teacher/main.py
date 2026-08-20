"""Application entry point."""

from __future__ import annotations

import signal
import sys

from .dispatcher import Dispatcher
from .utils.config import get_settings
from .utils.logger import get_logger
from .wcf_client import WcfClient

log = get_logger()
settings = get_settings()


def _validate_env() -> None:
    missing = []
    # Volcano is the primary key (vision + text). If it's not set, fall back
    # to DashScope (for Qwen-VL) + DeepSeek.
    if not settings.volc_api_key or settings.volc_api_key.startswith("your-"):
        if not settings.dashscope_api_key or settings.dashscope_api_key.startswith("sk-your"):
            missing.append("DASHSCOPE_API_KEY (火山 key 未填时必填)")
        if not settings.deepseek_api_key or settings.deepseek_api_key.startswith("sk-your"):
            missing.append("DEEPSEEK_API_KEY (火山 key 未填时必填)")
    if not settings.teacher_wxid:
        missing.append("WCF_TEACHER_WXID")
    if not settings.whitelist_groups:
        missing.append("WCF_WHITELIST_GROUPS")
    if missing:
        log.error(f"请在 .env 中设置: {', '.join(missing)}")
        sys.exit(1)


def main() -> None:
    _validate_env()
    log.info("=" * 60)
    log.info("AI 批改小助手启动中...")
    log.info(f"监听群: {settings.whitelist_groups}")
    log.info(f"指定老师: {settings.teacher_wxid}")
    log.info("=" * 60)

    wcf = WcfClient()
    dispatcher = Dispatcher(wcf)

    def _on_msg(msg):
        dispatcher.handle(msg)

    def _shutdown(signum, frame):  # noqa: ARG001
        log.info(f"received signal {signum}, shutting down ...")
        wcf.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    wcf.start()
    wcf.on_message(_on_msg)
    log.info("ready. waiting for messages ...")
    wcf.keep_running()


if __name__ == "__main__":
    main()
