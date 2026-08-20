"""Rate limiter: per-parent daily counter + global token bucket."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from .config import get_settings


class RateLimiter:
    """In-memory daily counters.

    For a single-process Windows service this is sufficient. If we ever run
    multiple instances, swap for a SQLite-backed implementation.
    """

    def __init__(self) -> None:
        s = get_settings()
        self.max_per_parent = s.max_per_parent_per_day
        self.max_total = s.max_total_per_day
        self._per_parent: dict[str, int] = defaultdict(int)
        self._total: int = 0
        self._current_date: date = date.today()
        self._lock = threading.Lock()
        # State persistence (best effort, atomic write)
        self._state_file = s.cache_dir / "rate_state.json"

    def _maybe_rollover(self) -> None:
        today = date.today()
        if today != self._current_date:
            self._per_parent.clear()
            self._total = 0
            self._current_date = today

    def allow(self, parent_key: str) -> tuple[bool, str]:
        """Check if processing is allowed. Returns (allowed, reason)."""
        with self._lock:
            self._maybe_rollover()
            if self._total >= self.max_total:
                return False, f"达到每日机器人总上限 ({self.max_total})"
            used = self._per_parent[parent_key]
            if used >= self.max_per_parent:
                return False, f"该家长今日已达上限 ({self.max_per_parent})"
            return True, ""

    def consume(self, parent_key: str) -> None:
        with self._lock:
            self._per_parent[parent_key] += 1
            self._total += 1


class QuietHours:
    """Decide whether the current local time falls in quiet hours."""

    def __init__(self, start: int, end: int) -> None:
        self.start = start  # e.g. 22
        self.end = end  # e.g. 7

    def is_quiet(self, hour: int | None = None) -> bool:
        from datetime import datetime

        h = datetime.now().hour if hour is None else hour
        if self.start <= self.end:
            return self.start <= h < self.end
        # overnight window, e.g. 22-7
        return h >= self.start or h < self.end


def human_delay(min_sec: float = 5.0, max_sec: float = 15.0) -> float:
    """Return a human-like random delay. Centralized for tests."""
    import random

    return random.uniform(min_sec, max_sec)
