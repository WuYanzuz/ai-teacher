"""Teacher private-chat command parser."""

from __future__ import annotations

import re

RE_REGISTER = re.compile(r"记住\s+(\S+)\s+是\s+(\S+)")
RE_UNREGISTER = re.compile(r"删除\s+(\S+)")
REPORT_KEYWORDS = ("成长", "报告", "小结", "近况")


def parse_command(text: str) -> dict | None:
    """Return a dict like {"action": "register", "wxid": ..., "name": ...} or None."""
    text = text.strip()

    m = RE_REGISTER.search(text)
    if m:
        return {"action": "register", "wxid": m.group(1), "name": m.group(2)}

    m = RE_UNREGISTER.search(text)
    if m:
        return {"action": "unregister", "wxid": m.group(1)}

    # Growth report: remove all report keywords, then strip trailing 的
    if any(kw in text for kw in REPORT_KEYWORDS):
        cleaned = text
        for kw in REPORT_KEYWORDS:
            cleaned = cleaned.replace(kw, "")
        name = cleaned.strip().rstrip("的").strip()
        if name:
            return {"action": "report", "name": name}

    if text in ("帮助", "help", "?"):
        return {"action": "help"}

    if text in ("清空", "清理缓存"):
        return {"action": "cleanup"}

    return None


HELP_TEXT = (
    "可用指令:\n"
    "记住 <wxid> 是 <孩子名>     把家长 wxid 绑到孩子名\n"
    "删除 <wxid>                  解绑\n"
    "<孩子名>的成长/报告/小结    查看某孩子的成长总结\n"
    "清空/清理缓存                清理 30 天前的临时文件\n"
    "帮助                          显示本帮助"
)
