"""Teacher private-chat command parser.

Supported commands:
  记住 <wxid> 是 <孩子名>     bind parent wxid to child name
  绑定 <群昵称> 是 <孩子名>   bind group nick pattern to child name
  删除 <wxid>                  unbind
  <孩子名>的成长/报告/小结     get growth report
  ✓/对                        confirm the last homework as correctly attributed
  ×/忽略                      mark the last homework as not-a-homework
  撤销                         revert the last action
  帮助                         show this help
"""

from __future__ import annotations

import re
from collections import deque
from typing import Optional

RE_REGISTER = re.compile(r"记住\s+(\S+)\s+是\s+(\S+)")
RE_BIND_NICK = re.compile(r"绑定\s+(\S+)\s+是\s+(\S+)")
RE_UNREGISTER = re.compile(r"删除\s+(\S+)")
REPORT_KEYWORDS = ("成长", "报告", "小结", "近况")


# In-memory action log for the most recent homework, so teacher can
# 撤销 / ✓ / × within a short window.
# Each entry: {"parent_wxid": str, "child_name": str, "homework_id": int, "ts": float}
_RECENT: deque = deque(maxlen=50)


def push_recent(entry: dict) -> None:
    _RECENT.append(entry)


def pop_recent(parent_wxid: Optional[str] = None) -> dict | None:
    """Get the most recent entry, optionally filtered by parent_wxid."""
    if not _RECENT:
        return None
    if parent_wxid is None:
        return _RECENT[-1]
    for entry in reversed(_RECENT):
        if entry.get("parent_wxid") == parent_wxid:
            return entry
    return None


def parse_command(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None

    # Quick ack / ignore / revert
    if text in ("✓", "对", "是的", "确认"):
        return {"action": "ack"}
    if text in ("×", "忽略", "不算", "不是作业"):
        return {"action": "ignore"}
    if text in ("撤销", "撤回"):
        return {"action": "revert"}

    m = RE_REGISTER.search(text)
    if m:
        return {"action": "register", "wxid": m.group(1), "name": m.group(2)}

    m = RE_BIND_NICK.search(text)
    if m:
        return {"action": "bind_nick", "pattern": m.group(1), "name": m.group(2)}

    m = RE_UNREGISTER.search(text)
    if m:
        return {"action": "unregister", "wxid": m.group(1)}

    # "这是 XX" -> rename last homework
    m = re.match(r"这[是個]?\s*(\S+)", text)
    if m:
        return {"action": "rename", "name": m.group(1)}

    # "<name>的成长" etc.
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
    "📋 可用指令\n"
    "────────────────\n"
    "记住 <wxid> 是 <孩子名>     绑定家长 wxid\n"
    "绑定 <群昵称> 是 <孩子名>   按群昵称绑定\n"
    "删除 <wxid>                  解除绑定\n"
    "────────────────\n"
    "✓ / 对                       确认上条作业归属正确\n"
    "× / 忽略                     标记上条不是作业\n"
    "撤销                          撤回上条评价\n"
    "这是 XX                       改孩子名\n"
    "────────────────\n"
    "<孩子名>的成长/报告/小结     查看成长总结\n"
    "清空                          清理 30 天前的临时文件\n"
    "帮助                          显示本帮助"
)
