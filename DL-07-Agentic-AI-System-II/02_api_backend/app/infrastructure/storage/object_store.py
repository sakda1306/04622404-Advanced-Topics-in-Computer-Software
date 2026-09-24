"""S3-compatible object storage for data exports (MinIO in development, D-84).

The MinIO client is synchronous, so calls run in a thread. Download links are signed
with a second client configured for the public URL: the signature covers the host, and
the browser reaches the storage under a different name than the services do. Signing
needs no network call because the region is fixed.
"""

from __future__ import annotations

import asyncio
import io
from datetime import timedelta
from urllib.parse import urlsplit

from minio import Minio
from minio.error import S3Error

from app.core.config import ObjectStorageSettings


def _client(endpoint: str, settings: ObjectStorageSettings, *, secure: bool) -> Minio:
    secret = settings.object_storage_secret_key
    return Minio(
        endpoint,
        access_key=settings.object_storage_access_key,
        secret_key=secret.get_secret_value() if secret else None,
        secure=secure,
        region=settings.object_storage_region,
    )


class MinioObjectStore:
    def __init__(self, settings: ObjectStorageSettings) -> None:
        if not settings.enabled or settings.object_storage_endpoint is None:
            raise ValueError("object storage is not configured")
        self._bucket = settings.object_storage_bucket
        self._client = _client(
            settings.object_storage_endpoint, settings, secure=settings.object_storage_secure
        )
        public = urlsplit(settings.object_storage_public_url or "")
        if public.netloc:
            self._signer = _client(public.netloc, settings, secure=public.scheme == "https")
        else:
            self._signer = self._client
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        if not self._client.bucket_exists(self._bucket):
            try:
                self._client.make_bucket(self._bucket)
            except S3Error as exc:
                # Another process created it first.
                if exc.code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    raise
        self._bucket_ready = True

    def _put(self, key: str, data: bytes, content_type: str) -> None:
        self._ensure_bucket()
        self._client.put_object(
            self._bucket, key, io.BytesIO(data), len(data), content_type=content_type
        )

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        await asyncio.to_thread(self._put, key, data, content_type)

    def _put_file(self, key: str, path: str, content_type: str) -> None:
        self._ensure_bucket()
        self._client.fput_object(self._bucket, key, path, content_type=content_type)

    async def put_file(self, key: str, path: str, *, content_type: str) -> None:
        """Upload from disk in parts, so a large export never sits in memory."""
        await asyncio.to_thread(self._put_file, key, path, content_type)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.remove_object, self._bucket, key)

    async def download_url(self, key: str, *, expires_seconds: int) -> str:
        return await asyncio.to_thread(
            self._signer.presigned_get_object,
            self._bucket,
            key,
            expires=timedelta(seconds=expires_seconds),
        )
