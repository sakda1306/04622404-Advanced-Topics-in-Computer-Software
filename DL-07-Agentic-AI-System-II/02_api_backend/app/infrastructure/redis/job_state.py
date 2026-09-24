"""Live job status and progress events (docs/03_data_design.md section 5.2).

`job:{id}` is a HASH with the current status; `job:{id}:events` is a STREAM that the
SSE endpoint and the synchronous wait both read (D-38). Stream entry ids are the
opaque SSE event ids. Both keys expire after P-05; PostgreSQL stays the source of truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from app.domain.enums import JobStage, JobStatus, JobType
from app.infrastructure.redis.keys import RedisKeys

TERMINAL_EVENTS = frozenset({"completed", "failed", "cancelled"})

# Only update a job that still exists, so a late update cannot create a partial hash, and
# never leave a terminal status, so a late worker cannot revive a cancelled job (D-73).
_UPDATE = """
if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end
local status = redis.call('HGET', KEYS[1], 'status')
if status == 'succeeded' or status == 'failed' or status == 'cancelled' then return 0 end
redis.call('HSET', KEYS[1], unpack(ARGV, 2))
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
return 1
"""


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    job_id: UUID
    user_id: UUID
    type: JobType
    status: JobStatus
    stage: JobStage
    progress: int
    recommendation_id: UUID | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class JobEvent:
    id: str
    event: str
    data: dict[str, Any]

    @property
    def terminal(self) -> bool:
        return self.event in TERMINAL_EVENTS


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


class RedisJobStateStore:
    def __init__(
        self, redis: Redis, keys: RedisKeys, *, ttl_seconds: int, max_events: int = 100
    ) -> None:
        self._redis = redis
        self._keys = keys
        self._ttl = ttl_seconds
        self._max_events = max_events
        self._update = redis.register_script(_UPDATE)

    async def create(self, snapshot: JobSnapshot) -> None:
        key = self._keys.job(snapshot.job_id)
        fields = {
            "user_id": str(snapshot.user_id),
            "type": snapshot.type.value,
            "status": snapshot.status.value,
            "stage": snapshot.stage.value,
            "progress": str(snapshot.progress),
            "recommendation_id": str(snapshot.recommendation_id or ""),
            "error_code": snapshot.error_code or "",
            "created_at": snapshot.created_at.isoformat(),
            "updated_at": snapshot.updated_at.isoformat(),
        }
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=fields)
            pipe.expire(key, self._ttl)
            await pipe.execute()

    async def update(
        self,
        job_id: UUID,
        *,
        updated_at: datetime,
        status: JobStatus | None = None,
        stage: JobStage | None = None,
        progress: int | None = None,
        error_code: str | None = None,
    ) -> None:
        pairs: list[str] = ["updated_at", updated_at.isoformat()]
        for name, value in (
            ("status", status.value if status else None),
            ("stage", stage.value if stage else None),
            ("progress", str(progress) if progress is not None else None),
            ("error_code", error_code),
        ):
            if value is not None:
                pairs += [name, value]
        await self._update(keys=[self._keys.job(job_id)], args=[self._ttl, *pairs])

    async def publish(self, job_id: UUID, event: str, data: dict[str, Any]) -> str:
        key = self._keys.job_events(job_id)
        fields = {"event": event, "data": json.dumps(data, ensure_ascii=False)}
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.xadd(key, fields, maxlen=self._max_events, approximate=True)  # type: ignore[arg-type]
            pipe.expire(key, self._ttl)
            entry_id, _ = await pipe.execute()
        return _text(entry_id)

    async def get(self, job_id: UUID) -> JobSnapshot | None:
        raw: dict[Any, Any] = await self._redis.hgetall(self._keys.job(job_id))  # type: ignore[misc]
        if not raw:
            return None
        data = {_text(k): _text(v) for k, v in raw.items()}
        return JobSnapshot(
            job_id=job_id,
            user_id=UUID(data["user_id"]),
            type=JobType(data["type"]),
            status=JobStatus(data["status"]),
            stage=JobStage(data["stage"]),
            progress=int(data["progress"]),
            recommendation_id=UUID(data["recommendation_id"])
            if data["recommendation_id"]
            else None,
            error_code=data["error_code"] or None,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    async def read(self, job_id: UUID, *, after: str, block_ms: int | None) -> list[JobEvent]:
        """Events after the given stream id ("0-0" = from the start)."""
        result = await self._redis.xread(
            {self._keys.job_events(job_id): after}, count=100, block=block_ms
        )
        events: list[JobEvent] = []
        for _stream, entries in result or []:
            for entry_id, fields in entries:
                values = {_text(k): _text(v) for k, v in fields.items()}
                events.append(
                    JobEvent(_text(entry_id), values["event"], json.loads(values["data"]))
                )
        return events
