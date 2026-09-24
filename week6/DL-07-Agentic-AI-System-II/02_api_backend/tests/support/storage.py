"""In-memory object storage for tests (same interface as MinioObjectStore)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MemoryObjectStore:
    objects: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    fail_on_put: bool = False

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        if self.fail_on_put:
            raise ConnectionError("storage down")
        self.objects[key] = (data, content_type)

    async def put_file(self, key: str, path: str, *, content_type: str) -> None:
        data = await asyncio.to_thread(Path(path).read_bytes)
        await self.put(key, data, content_type=content_type)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def download_url(self, key: str, *, expires_seconds: int) -> str:
        return f"https://storage.example/{key}?expires={expires_seconds}"
