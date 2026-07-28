"""Object storage for generated artifacts (PDF, DXF, XLSX, AI renders).

Cloudflare R2 rather than GCS: 10 GB free, and — the reason that matters at
consumer scale — zero egress fees. R2 speaks the S3 API, so boto3 works with
region_name='auto' and an account-scoped endpoint.

Unconfigured deployments get NullStorage so CI and local dev need no
credentials and no network.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get_bytes(self, key: str) -> bytes | None: ...
    def signed_url(self, key: str, ttl_seconds: int = 900) -> str: ...


class NullStorage:
    """No-op backend used when R2 is not configured."""

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        return None

    async def get_bytes(self, key: str) -> bytes | None:
        return None

    def signed_url(self, key: str, ttl_seconds: int = 900) -> str:
        return ""


class R2Storage:
    def __init__(
        self, account_id: str, access_key_id: str, secret_access_key: str, bucket: str
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                region_name="auto",
                config=Config(signature_version="s3v4"),
            )
        return self._client

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        def _put() -> None:
            self._get_client().put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
            )

        await asyncio.to_thread(_put)

    async def get_bytes(self, key: str) -> bytes | None:
        def _get() -> bytes | None:
            client = self._get_client()
            try:
                resp = client.get_object(Bucket=self.bucket, Key=key)
                return resp["Body"].read()
            except client.exceptions.NoSuchKey:
                return None

        return await asyncio.to_thread(_get)

    def signed_url(self, key: str, ttl_seconds: int = 900) -> str:
        return self._get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )


def build_storage(cfg) -> StorageBackend:
    required = (
        cfg.r2_account_id,
        cfg.r2_access_key_id,
        cfg.r2_secret_access_key,
        cfg.r2_bucket,
    )
    if not all(required):
        logger.info("R2 not configured — artifacts stream inline, nothing is cached.")
        return NullStorage()
    return R2Storage(*required)


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        from app.config.settings import settings

        _storage = build_storage(settings)
    return _storage
