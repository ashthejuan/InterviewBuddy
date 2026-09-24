"""S3-compatible object storage (Cloudflare R2 / local MinIO)."""

from __future__ import annotations

import uuid
from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import Settings, get_settings


class StorageError(RuntimeError):
    pass


def _client(settings: Settings) -> BaseClient:
    endpoint = (settings.r2_endpoint_url or "").strip() or "http://localhost:9000"
    region = settings.r2_region if settings.r2_region and settings.r2_region != "auto" else "us-east-1"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.r2_access_key_id or "minioadmin",
        aws_secret_access_key=settings.r2_secret_access_key or "minioadmin",
        region_name=region,
        config=Config(s3={"addressing_style": "path"}),
    )


@lru_cache
def ensure_bucket(settings_key: str = "default") -> None:
    """Create bucket once per process if missing (local MinIO)."""
    del settings_key
    settings = get_settings()
    client = _client(settings)
    bucket = settings.r2_bucket
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        try:
            client.create_bucket(Bucket=bucket)
        except ClientError as exc:
            # Race: another worker created it
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise StorageError(f"could not ensure bucket {bucket}: {exc}") from exc


def build_object_key(
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    document_id: uuid.UUID,
    filename: str,
) -> str:
    safe = filename.replace("/", "_").replace("\\", "_")
    return f"users/{user_id}/sessions/{session_id}/{document_id}/{safe}"


def put_bytes(
    *,
    key: str,
    data: bytes,
    content_type: str,
    settings: Settings | None = None,
) -> tuple[str, str]:
    """Upload bytes; returns (bucket, key)."""
    cfg = settings or get_settings()
    ensure_bucket()
    client = _client(cfg)
    try:
        client.put_object(
            Bucket=cfg.r2_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    except ClientError as exc:
        raise StorageError(f"upload failed: {exc}") from exc
    return cfg.r2_bucket, key
