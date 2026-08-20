"""Smoke tests that don't require any external service."""

from __future__ import annotations

from pathlib import Path
import sys

# Make the project importable when run from any cwd
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def test_parse_nickname_basic():
    from ai_teacher.child_id.resolver import parse_nickname
    assert parse_nickname("小明爸").name == "小明"
    assert parse_nickname("李小花妈妈").name == "李小花"
    assert parse_nickname("Lily妈妈").name == "Lily"
    assert parse_nickname("爷爷").name == "爷爷"  # whole thing kept, low confidence


def test_parse_nickname_emoji():
    from ai_teacher.child_id.resolver import parse_nickname
    g = parse_nickname("小明爸👨")
    assert g is not None
    assert g.name == "小明"


def test_resolver_registry_priority():
    from ai_teacher.child_id.resolver import ChildIdResolver
    r = ChildIdResolver()
    r.register("wxid_abc", "官方小明")
    g = r.resolve("wxid_abc", group_nickname="别的小明爸")
    assert g.name == "官方小明"
    assert g.source == "registry"


def test_resolver_fallback_hash():
    from ai_teacher.child_id.resolver import ChildIdResolver
    r = ChildIdResolver()
    g = r.resolve("wxid_unknown", group_nickname=None)
    assert g.name.startswith("匿名-")
    assert g.source == "hash"


def test_command_parser():
    from ai_teacher.teacher.commands import parse_command
    assert parse_command("记住 wxid_abc 是 小明") == {
        "action": "register", "wxid": "wxid_abc", "name": "小明"
    }
    assert parse_command("删除 wxid_abc") == {"action": "unregister", "wxid": "wxid_abc"}
    assert parse_command("小明的成长") == {"action": "report", "name": "小明"}
    assert parse_command("帮助") == {"action": "help"}


def test_retry_eventually_succeeds():
    from ai_teacher.utils.retry import with_retry
    calls = {"n": 0}

    @with_retry(max_attempts=3, backoff=1.0, initial_delay=0.01)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("boom")
        return 42

    assert flaky() == 42
    assert calls["n"] == 2


def test_quiet_hours():
    from ai_teacher.utils.ratelimit import QuietHours
    q = QuietHours(22, 7)
    assert q.is_quiet(23) is True
    assert q.is_quiet(2) is True
    assert q.is_quiet(10) is False
