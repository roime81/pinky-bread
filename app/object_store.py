from __future__ import annotations

import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, SessionLocal
from .settings import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StoredObjectRecord(Base):
    """Relational metadata for bytes stored in local or S3-compatible object storage."""

    __tablename__ = "stored_objects"
    __table_args__ = (
        Index("ix_stored_objects_company_created", "company_id", "created_at"),
        Index("ix_stored_objects_owner", "tenant_id", "owner_type", "owner_id"),
    )

    object_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    owner_type: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[str] = mapped_column(String(120), index=True)
    object_key: Mapped[str] = mapped_column(String(700), unique=True)
    storage_backend: Mapped[str] = mapped_column(String(24))
    storage_uri: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


def _object_dict(record: StoredObjectRecord) -> dict[str, Any]:
    return {
        "object_id": record.object_id,
        "tenant_id": record.tenant_id,
        "company_id": record.company_id,
        "owner_type": record.owner_type,
        "owner_id": record.owner_id,
        "object_key": record.object_key,
        "storage_backend": record.storage_backend,
        "storage_uri": record.storage_uri,
        "filename": record.filename,
        "content_type": record.content_type,
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
        "created_by": record.created_by,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "metadata": record.metadata_json or {},
    }


class ObjectStore:
    """S3-compatible storage adapter with safe local development mode.

    PostgreSQL stores metadata; the adapter stores file bytes. The S3 mode
    supports SeaweedFS and other S3-compatible open-source object stores.
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

    def persist_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str,
        tenant_id: str,
        owner_type: str,
        owner_id: str,
        filename: str,
        created_by: str,
        company_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        object_id = str(uuid.uuid4())
        safe_key = self._safe_key(key)
        storage_uri = self.put_bytes(safe_key, content, content_type)
        record = StoredObjectRecord(
            object_id=object_id,
            tenant_id=tenant_id,
            company_id=company_id,
            owner_type=owner_type,
            owner_id=owner_id,
            object_key=safe_key,
            storage_backend=self.settings.storage_backend,
            storage_uri=storage_uri,
            filename=Path(filename).name[:255],
            content_type=(content_type or "application/octet-stream")[:200],
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            created_by=created_by,
            metadata_json=metadata or {},
        )
        try:
            with SessionLocal() as db:
                db.add(record)
                db.commit()
                db.refresh(record)
                return _object_dict(record)
        except Exception:
            # Avoid an orphaned object if the metadata transaction fails.
            self.delete(safe_key)
            raise

    def get_record(self, *, object_id: str, tenant_id: str, company_id: str) -> dict[str, Any] | None:
        with SessionLocal() as db:
            record = db.query(StoredObjectRecord).filter(
                StoredObjectRecord.object_id == object_id,
                StoredObjectRecord.tenant_id == tenant_id,
                StoredObjectRecord.company_id == company_id,
            ).first()
            return _object_dict(record) if record else None

    def list_records(self, *, tenant_id: str, company_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with SessionLocal() as db:
            records = (
                db.query(StoredObjectRecord)
                .filter(
                    StoredObjectRecord.tenant_id == tenant_id,
                    StoredObjectRecord.company_id == company_id,
                )
                .order_by(StoredObjectRecord.created_at.desc())
                .limit(min(max(limit, 1), 500))
                .all()
            )
            return [_object_dict(record) for record in records]

    def get_bytes(self, key: str, backend: str | None = None) -> bytes:
        safe_key = self._safe_key(key)
        selected_backend = backend or self.settings.storage_backend
        if selected_backend == "s3":
            response = self._s3_client().get_object(Bucket=self.settings.s3_bucket, Key=safe_key)
            return response["Body"].read()
        if selected_backend != "local":
            raise ValueError(f"Unsupported storage backend: {selected_backend}")

        root = (self.settings.upload_dir / "objects").resolve()
        source = (root / safe_key).resolve()
        if root not in source.parents or not source.is_file():
            raise FileNotFoundError(safe_key)
        return source.read_bytes()

    def delete(self, key: str, backend: str | None = None) -> None:
        safe_key = self._safe_key(key)
        selected_backend = backend or self.settings.storage_backend
        if selected_backend == "s3":
            self._s3_client().delete_object(Bucket=self.settings.s3_bucket, Key=safe_key)
            return
        if selected_backend != "local":
            raise ValueError(f"Unsupported storage backend: {selected_backend}")
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
            # This development identity needs bucket administration on first run.
            # In production, pre-create the bucket and remove the Admin capability.
            client.create_bucket(Bucket=self.settings.s3_bucket)
