"""Decide whether a media message is homework worth grading."""

from __future__ import annotations

from pathlib import Path

from ..utils.logger import get_logger

log = get_logger()


class HomeworkClassifier:
    """Two-stage gate: cheap pre-filter -> expensive VL check."""

    # Cheap pre-filter: must look like media + group size + sender plausibility
    def quick_filter(self, *, msg_type: int, file_size_bytes: int, sender_wxid: str) -> bool:
        if msg_type not in (3, 34, 43):  # image, voice, video
            return False
        if file_size_bytes <= 1024:  # < 1KB is almost certainly not real media
            return False
        if file_size_bytes > 100 * 1024 * 1024:  # > 100MB, likely not homework
            return False
        if not sender_wxid:
            return False
        return True

    def looks_like_homework(
        self,
        image_path: Path,
        transcript: str | None = None,
    ) -> bool:
        from .vision_router import get_vision_client

        try:
            return get_vision_client().is_homework_image(image_path, transcript=transcript)
        except Exception as e:
            log.exception(f"VL classify failed: {e}")
            return False
