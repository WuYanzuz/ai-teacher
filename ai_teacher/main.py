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
    # Aliyun Bailian is the new primary. Volcano / DashScope are fallbacks.
    has_aliyun = settings.aliyun_api_key and not settings.aliyun_api_key.startswith("sk-your")
    has_volc = settings.volc_api_key and not settings.volc_api_key.startswith("your-")
    has_dashscope = settings.dashscope_api_key and not settings.dashscope_api_key.startswith("sk-your")
    has_deepseek = settings.deepseek_api_key and not settings.deepseek_api_key.startswith("sk-your")

    if not (has_aliyun or has_volc or has_dashscope or has_deepseek):
        missing.append("ALIYUN_API_KEY (或 VOLC_API_KEY / DASHSCOPE_API_KEY)")

    if not settings.teacher_wxid or settings.teacher_wxid == "wxid_teacher":
        missing.append("WCF_TEACHER_WXID")
    if not settings.whitelist_groups or settings.whitelist_groups == ["1234567890@chatroom"]:
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
