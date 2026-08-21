"""Batch run the demo pipeline on every file in a directory.

Outputs a markdown report (printed + saved to data/batch_report.md) with
one row per file: classify, raw feedback, polished feedback, elapsed time.

Usage:
    python scripts/batch_test.py test/
    python scripts/batch_test.py test/ --child "我的小宝贝"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai_teacher.media import audio as audio_mod
from ai_teacher.media import video as video_mod
from ai_teacher.media.image import compress_image, is_image
from ai_teacher.utils.config import get_settings
from ai_teacher.utils.helpers import safe_filename
from ai_teacher.utils.logger import get_logger

log = get_logger()


# --- inline step implementations (lighter than demo_pipeline.py) ---

def _step_load(src: Path, out_dir: Path):
    """Load + extract frames + audio. Returns (frames, audio, media_type)."""
    if is_image(src):
        if src.suffix.lower() in (".jpg", ".jpeg"):
            jpg = src
        else:
            jpg = compress_image(src)
        return [jpg], None, "image"
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = video_mod.extract_frames(src, out_dir)
    audio_path = None
    try:
        from ai_teacher.media.ffmpeg_utils import require_ffmpeg
        import subprocess
        audio_path = out_dir / "audio.wav"
        subprocess.run(
            [require_ffmpeg(), "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(audio_path)],
            check=False, capture_output=True,
        )
        if not audio_path.exists() or audio_path.stat().st_size < 1024:
            audio_path = None
    except Exception:
        audio_path = None
    return frames, audio_path, "video"


def _transcribe(audio_path, mock: bool) -> str:
    if mock or audio_path is None:
        return ""
    from ai_teacher.ai.paraformer_client import ParaformerClient
    try:
        return ParaformerClient().transcribe_file(audio_path)
    except Exception as e:
        log.warning(f"transcribe failed: {e}")
        return ""


def _classify(frames, transcript: str, mock: bool) -> tuple[bool, str]:
    if mock:
        return True, "YES (mock)"
    from ai_teacher.ai.classifier import HomeworkClassifier
    clf = HomeworkClassifier()
    is_hw = clf.looks_like_homework(frames[0], transcript=transcript)
    return is_hw, "YES" if is_hw else "NO"


def _grade(frames, transcript: str, mock: bool) -> str:
    if mock:
        return "【mock】亮点: ...建议: ...鼓励: ..."
    from ai_teacher.ai.vision_router import get_vision_client
    try:
        return get_vision_client().grade_homework(frames, transcript=transcript)
    except Exception as e:
        log.exception(f"grade failed: {e}")
        return f"[GRADE_ERROR] {e}"


def _polish(raw: str, mock: bool) -> str:
    if mock:
        return raw
    from ai_teacher.ai.deepseek_client import TextClient
    try:
        return TextClient().polish(raw)
    except Exception as e:
        log.warning(f"polish failed: {e}")
        return raw


# --- main loop ---

def process_one(src: Path, work_dir: Path, child_name: str, mock: bool) -> dict:
    t0 = time.time()
    out_dir = work_dir / safe_filename(src.stem)
    frames, audio_path, media_type = _step_load(src, out_dir)
    transcript = _transcribe(audio_path, mock=mock)
    is_hw, classify_label = _classify(frames, transcript, mock=mock)
    if not is_hw:
        return {
            "file": src.name, "type": media_type, "size_mb": src.stat().st_size / 1024 / 1024,
            "duration_s": "?", "transcript": transcript[:60] + ("..." if len(transcript) > 60 else ""),
            "is_homework": "NO", "raw_feedback": "(skipped — not homework)",
            "polished": "(skipped)", "elapsed_s": round(time.time() - t0, 1),
        }
    raw = _grade(frames, transcript, mock=mock)
    polished = _polish(raw, mock=mock)
    return {
        "file": src.name, "type": media_type, "size_mb": round(src.stat().st_size / 1024 / 1024, 1),
        "duration_s": round(audio_mod.wav_duration(audio_path), 1) if audio_path else 0,
        "transcript": transcript[:60] + ("..." if len(transcript) > 60 else ""),
        "is_homework": classify_label, "raw_feedback": raw, "polished": polished,
        "elapsed_s": round(time.time() - t0, 1),
    }


def render_markdown(results: list[dict], child_name: str) -> str:
    lines: list[str] = []
    lines.append(f"# AI 批改机器人 - 批量测试报告")
    lines.append(f"")
    lines.append(f"- 测试时间: {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- 测试文件数: {len(results)}")
    lines.append(f"- 孩子名: {child_name}")
    lines.append("")
    lines.append("## 汇总表")
    lines.append("")
    lines.append("| 文件 | 类型 | 大小 | 时长 | ASR 转写前 60 字 | 分类 | 耗时 |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r['file']} | {r['type']} | {r['size_mb']}MB | {r['duration_s']}s | "
            f"{r['transcript']!r} | {r['is_homework']} | {r['elapsed_s']}s |"
        )
    lines.append("")
    lines.append("## 详细点评")
    lines.append("")
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r['file']}")
        lines.append("")
        lines.append(f"- 类型: {r['type']}, 大小: {r['size_mb']}MB, 时长: {r['duration_s']}s")
        lines.append(f"- 分类: {r['is_homework']}, 耗时: {r['elapsed_s']}s")
        if r.get("transcript"):
            lines.append(f"- ASR 转写: {r['transcript']}")
        lines.append(f"")
        lines.append(f"**原始点评**:")
        lines.append(f"```")
        lines.append(r["raw_feedback"])
        lines.append(f"```")
        lines.append(f"**润色后 (发给老师)**:")
        lines.append(f"```")
        lines.append(r["polished"])
        lines.append(f"```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch test the demo pipeline on a directory of media")
    ap.add_argument("dir", help="Directory of media files (test/ by default)")
    ap.add_argument("--child", default="测试小朋友", help="Child name to embed in report")
    ap.add_argument("--mock", action="store_true", help="Skip real API calls")
    ap.add_argument("--out", default="data/batch_report.md", help="Output markdown report path")
    args = ap.parse_args()

    src_dir = Path(args.dir).resolve()
    if not src_dir.is_dir():
        print(f"not a directory: {src_dir}", file=sys.stderr)
        return 1
    media_files = sorted(
        f for f in src_dir.iterdir()
        if f.is_file() and f.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".m4v", ".jpg", ".jpeg", ".png", ".webp")
    )
    if not media_files:
        print(f"no media files in {src_dir}", file=sys.stderr)
        return 1

    print(f"Found {len(media_files)} media files in {src_dir}")
    work_dir = PROJECT_ROOT / "data" / "batch_test"
    work_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for i, src in enumerate(media_files, 1):
        print(f"\n[{i}/{len(media_files)}] processing {src.name} ...")
        try:
            r = process_one(src, work_dir, args.child, args.mock)
        except Exception as e:
            log.exception(f"failed on {src}")
            r = {
                "file": src.name, "type": "?", "size_mb": 0, "duration_s": 0,
                "transcript": "", "is_homework": "ERROR", "raw_feedback": str(e),
                "polished": "(error)", "elapsed_s": 0,
            }
        results.append(r)
        print(f"  -> {r['is_homework']}, {r['elapsed_s']}s")

    report = render_markdown(results, args.child)
    out_path = PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n报告已写入: {out_path}")
    print(f"\n{'='*60}\n{report}\n{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
