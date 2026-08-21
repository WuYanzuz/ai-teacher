"""Aliyun OSS uploader. Used to put local audio files at a public URL
so that paraformer-8k-v2 (file transcription) can download them.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from ..utils.config import get_settings
from ..utils.logger import get_logger

log = get_logger()


class OSSUploader:
    """Thin wrapper over oss2.Bucket."""

    def __init__(self) -> None:
        import oss2  # local import so the project still imports without it

        s = get_settings()
        if not (s.oss_key_id and s.oss_key_secret and s.oss_bucket):
            raise RuntimeError(
                "OSS not configured. Set ALIYUN_OSS_KEY_ID / KEY_SECRET / BUCKET in .env"
            )
        self._oss2 = oss2
        auth = oss2.Auth(s.oss_key_id, s.oss_key_secret)
        self.bucket = oss2.Bucket(auth, s.oss_endpoint, s.oss_bucket)
        self.bucket_name = s.oss_bucket
        self.endpoint = s.oss_endpoint
        # quick sanity check
        try:
            self.bucket.get_bucket_info()
        except Exception as e:
            raise RuntimeError(f"OSS connect failed: {e}") from e
        log.info(f"OSS ready: bucket={s.oss_bucket} endpoint={s.oss_endpoint}")

    def upload_audio(self, local_path: Path, *, expire_sec: int = 3600) -> str:
        """Upload a local audio file, return a signed URL valid for `expire_sec`."""
        if not local_path.exists():
            raise FileNotFoundError(local_path)

        # Unique object key to avoid collisions
        key = f"transcribe/{time.strftime('%Y%m%d')}/{uuid.uuid4().hex}_{local_path.name}"
        log.info(f"uploading {local_path.name} -> oss://{self.bucket_name}/{key}")
        self.bucket.put_object_from_file(key, str(local_path))

        url = self.bucket.sign_url("GET", key, expire_sec)
        log.info(f"signed URL valid {expire_sec}s: {url[:80]}...")
        return url, key

    def delete(self, key: str) -> None:
        """Delete an object by key. Best-effort."""
        try:
            self.bucket.delete_object(key)
            log.debug(f"deleted oss://{self.bucket_name}/{key}")
        except Exception as e:
            log.warning(f"oss delete failed for {key}: {e}")
