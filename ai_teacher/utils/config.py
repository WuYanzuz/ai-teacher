"""Configuration loader.

Reads .env (secrets) and config.yaml (structure) and exposes a single Settings object.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml() -> dict[str, Any]:
    cfg_path = PROJECT_ROOT / "config.yaml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


class Settings:
    """Singleton-style config holder."""

    def __init__(self) -> None:
        _load_env()
        self.yaml = _load_yaml()

        # API keys
        # 阿里百炼 (Aliyun Bailian / Model Studio)
        # 工作空间专用端点, 兼容 OpenAI 协议
        self.aliyun_api_key: str = os.getenv("ALIYUN_API_KEY", "")
        self.aliyun_base_url: str = os.getenv(
            "ALIYUN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        # 火山方舟 (Plan 套餐)
        self.volc_api_key: str = os.getenv("VOLC_API_KEY", "")
        self.volc_base_url: str = os.getenv(
            "VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3"
        )
        # 阿里 OSS (用于 paraformer-8k-v2 语音转写, 需上传公网 URL)
        self.oss_key_id: str = os.getenv("ALIYUN_OSS_KEY_ID", "")
        self.oss_key_secret: str = os.getenv("ALIYUN_OSS_KEY_SECRET", "")
        self.oss_bucket: str = os.getenv("ALIYUN_OSS_BUCKET", "")
        self.oss_endpoint: str = os.getenv("ALIYUN_OSS_ENDPOINT", "oss-cn-beijing.aliyuncs.com")
        # DashScope (标准, 备选) - 留空时自动用 ALIYUN_API_KEY (百炼和 DashScope 共用 key)
        self.dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIYUN_API_KEY", "")
        # DeepSeek 官方 (备选)
        self.deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

        # WeChat
        self.robot_nickname: str = os.getenv("WCF_ROBOT_NICKNAME", "AI批改小助手")
        raw = os.getenv("WCF_WHITELIST_GROUPS", "")
        self.whitelist_groups: list[str] = [s.strip() for s in raw.split(",") if s.strip()]
        self.teacher_wxid: str = os.getenv("WCF_TEACHER_WXID", "").strip()

        # Business limits
        self.max_per_parent_per_day: int = int(os.getenv("MAX_PER_PARENT_PER_DAY", "5"))
        self.max_total_per_day: int = int(os.getenv("MAX_TOTAL_PER_DAY", "80"))
        self.cache_retention_days: int = int(os.getenv("CACHE_RETENTION_DAYS", "30"))
        self.quiet_hour_start: int = int(os.getenv("QUIET_HOUR_START", "22"))
        self.quiet_hour_end: int = int(os.getenv("QUIET_HOUR_END", "7"))

        # Paths (override-able via yaml)
        paths_cfg = self.yaml.get("paths", {})
        self.cache_dir: Path = PROJECT_ROOT / paths_cfg.get("cache_dir", "data/cache")
        self.db_path: Path = PROJECT_ROOT / paths_cfg.get("db_path", "data/ai_teacher.db")
        self.log_dir: Path = PROJECT_ROOT / paths_cfg.get("log_dir", "data/logs")

        for p in (self.cache_dir, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)

        # Models
        self.models = self.yaml.get("models", {})
        # Media
        self.media_cfg = self.yaml.get("media", {})
        # Logging
        self.log_cfg = self.yaml.get("logging", {})

    def model(self, key: str) -> dict[str, Any]:
        return self.models.get(key, {})

    def media(self, key: str, default: Any = None) -> Any:
        return self.media_cfg.get(key, default)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
