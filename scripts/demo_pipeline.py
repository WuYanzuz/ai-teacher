"""End-to-end pipeline demo.

Usage:
    python scripts/demo_pipeline.py path/to/video.mp4
    python scripts/demo_pipeline.py path/to/video.mp4 --mock
    python scripts/demo_pipeline.py path/to/image.jpg --mock

The script runs the same pipeline the bot would run when a parent posts a
homework video in the group. It does NOT touch WeChat. It prints the exact
text the bot would send to the teacher via private chat.

Add --mock to use canned AI responses (no API key required) so you can see
the output format.
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
from ai_teacher.prompts import grader
from ai_teacher.utils.config import get_settings
from ai_teacher.utils.helpers import safe_filename
from ai_teacher.utils.logger import get_logger

log = get_logger()


# --------------------------------------------------------------------------
# Mock data — used when --mock is passed
# --------------------------------------------------------------------------
MOCK_TRANSCRIPT = (
    "妈妈你看,这是我做的小手工,用彩纸折了一只小兔子。"
    "它的耳朵长长的,还有红眼睛呢。"
)
MOCK_CLASSIFY = "YES"
MOCK_FEEDBACK = (
    "孩子用粉色和白色的彩纸认真地折出了一只小兔子,"
    "能看出他/她先折了身体再单独折耳朵,步骤清晰、动手能力不错。"
    "可以引导孩子再加点背景,比如草地或胡萝卜,让作品更丰富。"
    "小兔子真可爱,继续加油!"
)


def _step(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _human_seconds(s: float) -> str:
    return f"{s:.1f}s"


# --------------------------------------------------------------------------
# Pipeline steps
# --------------------------------------------------------------------------
def step_extract(video_path: Path, out_dir: Path) -> tuple[list[Path], Path | None]:
    _step("1) 抽帧 + 抽音")
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    frames = video_mod.extract_frames(video_path, out_dir)
    print(f"  frames: {len(frames)} ({_human_seconds(time.time() - t0)})")
    for f in frames:
        print(f"    - {f.name} ({f.stat().st_size//1024}KB)")

    # Try to extract audio
    audio_path: Path | None = None
    try:
        from ai_teacher.media.ffmpeg_utils import require_ffmpeg
        import subprocess

        audio_path = out_dir / "audio.wav"
        proc = subprocess.run(
            [require_ffmpeg(), "-y", "-i", str(video_path),
             "-ar", "16000", "-ac", "1", str(audio_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0 or not audio_path.exists() or audio_path.stat().st_size < 1024:
            audio_path = None
    except Exception as e:
        log.debug(f"audio extract failed: {e}")
        audio_path = None

    if audio_path:
        dur = audio_mod.wav_duration(audio_path)
        print(f"  audio: {audio_path.name} ({dur:.1f}s)")
    else:
        print("  audio: (no audio track)")
    return frames, audio_path


def step_transcribe(audio_path: Path | None, mock: bool) -> str:
    _step("2) 语音转写 (Paraformer)")
    if mock or audio_path is None:
        print(f"  [mock] -> {MOCK_TRANSCRIPT[:50]}...")
        return MOCK_TRANSCRIPT
    t0 = time.time()
    from ai_teacher.ai.paraformer_client import ParaformerClient
    txt = ParaformerClient().transcribe_file(audio_path)
    print(f"  -> {len(txt)} chars ({_human_seconds(time.time() - t0)})")
    print(f"  text: {txt[:120]}{'...' if len(txt) > 120 else ''}")
    return txt


def step_classify(frames: list[Path], transcript: str | None, mock: bool) -> bool:
    _step("3) 分类: 是不是作业? (vision provider)")
    if mock:
        print(f"  [mock] -> {MOCK_CLASSIFY}")
        return MOCK_CLASSIFY == "YES"
    t0 = time.time()
    from ai_teacher.ai.classifier import HomeworkClassifier
    is_hw = HomeworkClassifier().looks_like_homework(frames[0], transcript=transcript)
    print(f"  -> {'YES 是作业' if is_hw else 'NO 不是作业'} ({_human_seconds(time.time() - t0)})")
    return is_hw


def step_grade(frames: list[Path], transcript: str | None, mock: bool) -> str:
    _step("4) 点评 (vision provider + 提示词)")
    if mock:
        print(f"  [mock] ->")
        for line in MOCK_FEEDBACK.split("\n"):
            print(f"    {line}")
        return MOCK_FEEDBACK
    t0 = time.time()
    from ai_teacher.ai.vision_router import get_vision_client
    client = get_vision_client()
    feedback = client.grade_homework(frames, transcript=transcript)
    print(f"  -> {_human_seconds(time.time() - t0)}, {len(feedback)} chars")
    for line in feedback.split("\n"):
        print(f"    {line}")
    return feedback


def step_polish(feedback: str, mock: bool) -> str:
    _step("5) 润色 (DeepSeek)")
    if mock:
        polished = feedback  # no-op in mock
        print(f"  [mock] 跳过润色,直接使用原点评")
        return polished
    t0 = time.time()
    from ai_teacher.ai.deepseek_client import DeepSeekClient
    try:
        polished = DeepSeekClient().polish(feedback, style="温柔")
        print(f"  -> {_human_seconds(time.time() - t0)}")
    except Exception as e:
        log.warning(f"polish failed, using raw: {e}")
        polished = feedback
    for line in polished.split("\n"):
        print(f"    {line}")
    return polished


def step_format_teacher_message(
    *,
    child_name: str,
    media_type: str,
    polished: str,
    transcript: str | None,
) -> str:
    _step("6) 发给老师的私聊消息 (最终格式)")
    from datetime import datetime
    from ai_teacher.teacher.notifier import TeacherNotifier

    parts: list[str] = []
    parts.append(f"【新作业】{datetime.now().strftime('%m-%d %H:%M')}")
    parts.append(f"小朋友: {child_name}")
    parts.append(f"类型: {TeacherNotifier._type_label(media_type)}")
    if transcript:
        t = transcript[:80] + "..." if len(transcript) > 80 else transcript
        parts.append(f"语音转写: {t}")
    parts.append("---")
    parts.append(polished.strip())
    text = "\n".join(parts)
    print(text)
    return text


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="End-to-end pipeline demo")
    ap.add_argument("input", help="Path to a video or image file")
    ap.add_argument("--mock", action="store_true", help="Use canned AI responses")
    ap.add_argument("--child", default="小明", help="Child name for the demo output")
    ap.add_argument("--out", default="data/demo", help="Output directory")
    args = ap.parse_args()

    src = Path(args.input).resolve()
    if not src.exists():
        print(f"找不到文件: {src}", file=sys.stderr)
        return 1

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  AI 批改机器人 - 端到端 demo")
    print("=" * 60)
    print(f"  input:  {src}")
    print(f"  output: {out_dir}")
    print(f"  mock:   {args.mock}")

    if is_image(src):
        _step("1) 压缩图片")
        if src.suffix.lower() in (".jpg", ".jpeg"):
            jpg = src
            print(f"  已是 JPEG,跳过压缩: {jpg.name} ({jpg.stat().st_size//1024}KB)")
        else:
            jpg = compress_image(src)
            print(f"  压缩完成: {jpg.name} ({jpg.stat().st_size//1024}KB)")
        frames = [jpg]
        transcript = None
        media_type = "image"
    else:
        frames, audio_path = step_extract(src, out_dir / safe_filename(src.stem))
        transcript = step_transcribe(audio_path, mock=args.mock)
        media_type = "video"

    is_hw = step_classify(frames, transcript, mock=args.mock)
    if not is_hw:
        print()
        print("  >> 这条消息不是作业,机器人会静默忽略,不发点评")
        return 0

    feedback = step_grade(frames, transcript, mock=args.mock)
    polished = step_polish(feedback, mock=args.mock)
    msg = step_format_teacher_message(
        child_name=args.child,
        media_type=media_type,
        polished=polished,
        transcript=transcript,
    )

    _step("完成")
    print("  上述消息就是机器人会发给老师的私聊内容。")
    print("  真实环境差异:")
    print("    - 上游: 来自 wcferry 监听的微信群消息")
    print("    - 下游: 通过 wcf.send_text 发到老师 wxid")
    print("    - 落库: 同时写入 SQLite 的 homework 表")
    return 0


if __name__ == "__main__":
    sys.exit(main())
