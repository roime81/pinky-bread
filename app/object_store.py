from __future__ import annotations

from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from .settings import get_settings


class ObjectStore:
    """Small S3-compatible object-store adapter with a safe local development mode.

    PostgreSQL stores object metadata; this adapter stores the bytes. S3 mode
    works with SeaweedFS and other S3-compatible open-source services.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def put_bytes(self, key: str, content: bytes, content_type: str) -> str:
        safe_key = self._safe_key(key)
        if self.settings.storage_backend == "s3":
            client = self._s3_client()
            self._ensure_bucket(client)
            client.put_object(
                Bucket=self.settings.s3_bucket,
                Key=safe_key,
                Body=content,
                ContentType=content_type,
            )
            return f"s3://{self.settings.s3_bucket}/{safe_key}"

        root = (self.settings.upload_dir / "objects").resolve()
        destination = (root / safe_key).resolve()
        if root not in destination.parents:
            raise ValueError("Invalid object key")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination.as_uri()

    def get_bytes(self, key: str) -> bytes:
        safe_key = self._safe_key(key)
        if self.settings.storage_backend == "s3":
            response = self._s3_client().get_object(Bucket=self.settings.s3_bucket, Key=safe_key)
            return response["Body"].read()

        root = (self.settings.upload_dir / "objects").resolve()
        source = (root / safe_key).resolve()
        if root not in source.parents or not source.is_file():
            raise FileNotFoundError(safe_key)
        return source.read_bytes()

    def delete(self, key: str) -> None:
        safe_key = self._safe_key(key)
        if self.settings.storage_backend == "s3":
            self._s3_client().delete_object(Bucket=self.settings.s3_bucket, Key=safe_key)
            return
        root = (self.settings.upload_dir / "objects").resolve()
        source = (root / safe_key).resolve()
        if root not in source.parents:
            raise ValueError("Invalid object key")
        source.unlink(missing_ok=True)

    @staticmethod
    def _safe_key(key: str) -> str:
        path = PurePosixPath(key)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Object key must be a safe relative path")
        return str(path)

    def _s3_client(self):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("S3 storage requires boto3; install the project requirements") from exc

        return boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url or None,
            region_name=self.settings.s3_region,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    def _ensure_bucket(self, client) -> None:
        try:
            client.head_bucket(Bucket=self.settings.s3_bucket)
        except Exception:
            # The configured runtime identity needs bucket administration only
            # for first-run provisioning; restrict it after the bucket exists.
            client.create_bucket(Bucket=self.settings.s3_bucket)
