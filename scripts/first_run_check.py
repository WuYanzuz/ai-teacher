"""Pre-flight checks: ffmpeg available, .env present, packages importable."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []

    # 1. ffmpeg
    if not shutil.which("ffmpeg"):
        errors.append("ffmpeg 不在 PATH 中,请先安装 ffmpeg 并加入 PATH")
    else:
        print(f"[OK] ffmpeg: {shutil.which('ffmpeg')}")

    # 2. .env
    env = PROJECT_ROOT / ".env"
    if not env.exists():
        errors.append(".env 文件不存在,请从 .env.example 复制并填入 key")
    else:
        print("[OK] .env exists")

    # 3. Python deps
    for mod in ("dashscope", "openai", "peewee", "PIL", "loguru", "dotenv", "yaml"):
        try:
            __import__(mod)
        except Exception as e:
            errors.append(f"依赖 {mod} 未安装: {e}")
        else:
            print(f"[OK] import {mod}")

    # 4. wcferry
    try:
        import wcferry  # noqa: F401
        print("[OK] wcferry")
    except Exception as e:
        errors.append(f"wcferry 未安装: {e} (需要先装 wcferry 及其 DLL)")

    if errors:
        print("\n--- 发现问题 ---")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\n所有检查通过, 可以 `python run.py` 启动")
    return 0


if __name__ == "__main__":
    sys.exit(main())
