"""Resolve which child a group message belongs to.

The bot listens in a parent group where senders sign their kid's name into
their WeChat display name (common in China: "小明爸", "李小花妈妈"). This
module extracts the child's name from the sender's nickname, with a fallback
to a short hash of the wxid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..utils.helpers import short_hash

# 常见家长昵称后缀
_PARENT_SUFFIXES = (
    "爸爸", "妈妈", "爸", "妈", "爷爷", "奶奶", "外公", "外婆",
    "father", "mother", "mom", "dad",
    "家长", "家", "监护人",
)


@dataclass
class ChildGuess:
    name: str
    confidence: float  # 0.0 - 1.0
    source: str  # "nickname" | "registry" | "hash"


def parse_nickname(display_name: str) -> ChildGuess | None:
    """Try to extract a child name from a parent-style group nickname.

    Examples:
        "小明爸"     -> 小明
        "李小花妈妈"  -> 李小花
        "Xiao Wang 爸爸" -> Xiao Wang
        "Lily妈妈👧"  -> Lily
    """
    if not display_name:
        return None
    name = display_name.strip()

    # Strip leading "X的" / "X-"
    name = re.sub(r"^[的\-_\s]+", "", name)
    # Remove emoji and non-word CJK range outside the name
    name = re.sub(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]", "", name)
    # Strip parent suffix
    for suf in _PARENT_SUFFIXES:
        if name.endswith(suf) and len(name) > len(suf):
            child = name[: -len(suf)].strip()
            if child:
                return ChildGuess(name=child, confidence=0.9, source="nickname")
    # If it doesn't end with a known suffix, treat the whole thing as the name
    if 1 <= len(name) <= 12:
        return ChildGuess(name=name, confidence=0.4, source="nickname")
    return None


class ChildIdResolver:
    """Stateful resolver that prefers teacher-registered names."""

    def __init__(self) -> None:
        # wxid -> child_name (overrides any nickname parse)
        self._registry: dict[str, str] = {}

    def register(self, parent_wxid: str, child_name: str) -> None:
        self._registry[parent_wxid] = child_name.strip()

    def unregister(self, parent_wxid: str) -> None:
        self._registry.pop(parent_wxid, None)

    def resolve(self, parent_wxid: str, group_nickname: str | None = None) -> ChildGuess:
        if parent_wxid in self._registry:
            return ChildGuess(
                name=self._registry[parent_wxid],
                confidence=1.0,
                source="registry",
            )
        if group_nickname:
            guess = parse_nickname(group_nickname)
            if guess and guess.confidence >= 0.8:
                return guess
        # Fallback: short hash so we still have a stable identifier
        return ChildGuess(
            name=f"匿名-{short_hash(parent_wxid, 4)}",
            confidence=0.0,
            source="hash",
        )
