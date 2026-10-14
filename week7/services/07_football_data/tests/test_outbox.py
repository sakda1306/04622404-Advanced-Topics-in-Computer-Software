"""Recovery, request bounds and legacy report search tests without external credentials."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.db import Base, IndexTask, Job, Match, Standing, WeeklyReport, make_database
from app.football import current_season, match_payload
from app.main import create_app
from app.service import BANGKOK, INDEX_MAX_BYTES, FootballService, ServiceError
from tests.test_integration import example_match, report_payload


def document(number, text="Premier League match statistics"):
    return {
        "doc_id": f"fixtures-{current_season()}-team-{number}",
        "title": f"Fixtures for team {number}",
        "text": text,
        "category": "fixtures",
        "origin": "football-data.org",
        "season": current_season(),
        "matchweek": None,
        "team_ids": [number],
        "date": "2026-09-21",
        "fetched_at": "2026-09-21T09:00:00+07:00",
        "url": None,
    }


@asynccontextmanager
async def local_service(tmp_path, transport):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'football.db'}")
    engine, sessions = make_database(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        yield FootballService(settings, sessions, client)
    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_failure_keeps_only_failed_batch_and_retries(tmp_path):
    requests, indexed = [], {}

    async def transport(request):
        docs = json.loads(request.content)["documents"]
        requests.append(len(docs))
        assert len(request.content) <= INDEX_MAX_BYTES
        if len(requests) == 2:
            return httpx.Response(503)
        indexed.update({doc["doc_id"]: doc for doc in docs})
        return httpx.Response(200, json={"upserted": len(docs)})

    async with local_service(tmp_path, transport) as service:
        async with service.sessions() as db:
            # Synthetic season-sized volume: 380 matches + 38 tables + 20 fixture docs.
            await service._queue_documents(db, [document(i) for i in range(438)], str(uuid4()))
            await db.commit()
        with pytest.raises(ServiceError):
            await service.reconcile_index()
        status = await service.status()
        assert requests == [100, 100, 100, 100, 38]
        assert status["index_sync"]["pending"] == 100
        assert "503" in status["index_sync"]["last_error"]
        await service.reconcile_index()
        assert requests == [100, 100, 100, 100, 38, 100]
        assert len(indexed) == 438
        assert (await service.status())["index_sync"]["pending"] == 0


@pytest.mark.asyncio
async def test_upsert_changed_while_http_is_in_flight_keeps_new_outbox_work(tmp_path):
    indexed = {}
    calls = []
    newer = document(1, "New matchweek content")

    async def transport(request):
        docs = json.loads(request.content)["documents"]
        calls.append(docs[0]["text"])
        if len(calls) == 1:
            async with service.sessions() as db:
                await service._queue_documents(db, [newer], str(uuid4()))
                await db.commit()
        indexed.update({doc["doc_id"]: doc for doc in docs})
        return httpx.Response(200)

    async with local_service(tmp_path, transport) as service:
        async with service.sessions() as db:
            await service._queue_documents(db, [document(1, "Old matchweek content")], str(uuid4()))
            await db.commit()
        await service.reconcile_index()
        assert calls == ["Old matchweek content"]
        async with service.sessions() as db:
            pending = await db.get(IndexTask, newer["doc_id"])
            assert pending is not None
            assert pending.payload["text"] == "New matchweek content"
        await service.reconcile_index()
        assert calls == ["Old matchweek content", "New matchweek content"]
        assert indexed[newer["doc_id"]]["text"] == "New matchweek content"
        assert (await service.status())["index_sync"]["pending"] == 0


@pytest.mark.asyncio
async def test_failed_report_reconcile_does_not_skip_later_delete(tmp_path):
    deleted = []

    async def transport(request):
        assert request.method == "DELETE"
        deleted.append(request.url.path)
        return httpx.Response(200)

    async with local_service(tmp_path, transport) as service:
        season = current_season()
        report = report_payload(season, 5)
        report["status"] = "published"
        report["search_text_en"] = "x" * INDEX_MAX_BYTES
        stamp = datetime.now(BANGKOK)
        async with service.sessions() as db:
            db.add(WeeklyReport(season=season, matchweek=5, status="published", payload=report))
            db.add(
                IndexTask(
                    doc_id=f"weekly-{season}-mw05",
                    action="reconcile_report",
                    payload={"season": season, "matchweek": 5},
                    request_id=str(uuid4()),
                    updated_at=stamp,
                )
            )
            db.add(
                IndexTask(
                    doc_id=document(1)["doc_id"],
                    action="delete",
                    payload=None,
                    request_id=str(uuid4()),
                    updated_at=stamp + timedelta(seconds=1),
                )
            )
            await db.commit()
        with pytest.raises(ServiceError, match="Index batch exceeds"):
            await service.reconcile_index()
        assert deleted == [f"/index/{document(1)['doc_id']}"]
        async with service.sessions() as db:
            report_task = await db.get(IndexTask, f"weekly-{season}-mw05")
            assert report_task is not None
            assert "Index batch exceeds" in report_task.last_error
            assert await db.get(IndexTask, document(1)["doc_id"]) is None


@pytest.mark.asyncio
async def test_batch_limit_counts_utf8_bytes_and_rejects_oversized_document(tmp_path):
    counts = []

    async def transport(request):
        assert len(request.content) <= INDEX_MAX_BYTES
        counts.append(len(json.loads(request.content)["documents"]))
        return httpx.Response(200)

    async with local_service(tmp_path, transport) as service:
        async with service.sessions() as db:
            await service._queue_documents(
                db, [document(i, "ก" * 800_000) for i in range(3)], str(uuid4())
            )
            await db.commit()
        await service.reconcile_index()
        assert counts == [2, 1]
        async with service.sessions() as db:
            await service._queue_documents(db, [document(4, "x" * INDEX_MAX_BYTES)], str(uuid4()))
            await db.commit()
        with pytest.raises(ServiceError):
            await service.reconcile_index()
        assert counts == [2, 1]
        assert (await service.status())["index_sync"]["pending"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("published", [False, True])
async def test_startup_worker_recovers_503_and_young_crash_transition(tmp_path, published):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'football.db'}",
        index_retry_seconds=0.02,
        index_retry_max_seconds=0.05,
        index_transition_timeout_seconds=0.15,
    )
    engine, sessions = make_database(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    season = current_season()
    doc_id = f"weekly-{season}-mw05"
    payload = report_payload(season, 5)
    payload["status"] = "published" if published else "draft"
    async with sessions() as db:
        db.add(WeeklyReport(season=season, matchweek=5, status=payload["status"], payload=payload))
        db.add(
            IndexTask(
                doc_id=doc_id,
                action="transition",
                payload={"season": season, "matchweek": 5},
                request_id=str(uuid4()),
                updated_at=datetime.now(BANGKOK),
            )
        )
        db.add(
            IndexTask(
                doc_id=document(1)["doc_id"],
                action="upsert",
                payload=document(1),
                request_id=str(uuid4()),
                updated_at=datetime.now(BANGKOK),
            )
        )
        await db.commit()
    await engine.dispose()
    failed = asyncio.Event()
    ready = False
    indexed = {} if published else {doc_id: {"interrupted": True}}

    async def transport(request):
        if not ready:
            failed.set()
            return httpx.Response(503)
        if request.method == "DELETE":
            indexed.pop(request.url.path.removeprefix("/index/"), None)
        else:
            indexed.update({doc["doc_id"]: doc for doc in json.loads(request.content)["documents"]})
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as upstream:
        app = create_app(settings, http=upstream)
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(failed.wait(), timeout=2)
            service = app.state.service
            assert (await service.status())["index_sync"]["pending"] == 2
            ready = True
            async with asyncio.timeout(3):
                while (await service.status())["index_sync"]["pending"]:
                    await asyncio.sleep(0.01)
            assert (doc_id in indexed) is published
            assert document(1)["doc_id"] in indexed
            assert (await service.status())["index_sync"]["last_error"] is None


@pytest.mark.asyncio
async def test_edit_legacy_report_backfills_source_facts_before_publish(tmp_path):
    indexed = {}

    async def transport(request):
        indexed.update({doc["doc_id"]: doc for doc in json.loads(request.content)["documents"]})
        return httpx.Response(200)

    async with local_service(tmp_path, transport) as service:
        season = current_season()
        match = match_payload(example_match(season), "2026-09-21T09:00:00+07:00")
        payload = report_payload(season, 5)
        del payload["search_text_en"]
        async with service.sessions() as db:
            db.add(WeeklyReport(season=season, matchweek=5, status="draft", payload=payload))
            db.add(Standing(season=season, matchweek=5, payload={"rows": []}))
            db.add(
                Match(
                    match_id=match["match_id"],
                    external_id=12345,
                    season=season,
                    matchweek=5,
                    home_team_id=57,
                    away_team_id=61,
                    status="FINISHED",
                    payload=match,
                )
            )
            await db.commit()
        await service.edit_report(season, 5, None, "ผลที่ admin พิมพ์ 10-0", "beat")
        report = await service.publish(season, 5, "beat", str(uuid4()))
        text = indexed[f"weekly-{season}-mw05"]["text"]
        assert report["markdown"] == "ผลที่ admin พิมพ์ 10-0"
        assert report["search_text_policy"] == "source_facts"
        assert "Arsenal FC 2-1 Chelsea FC" in text
        assert "10-0" not in text


@pytest.mark.asyncio
async def test_historical_index_is_gated_and_batches_at_most_50(tmp_path):
    requests = []

    async def transport(request):
        docs = json.loads(request.content)["documents"]
        requests.append(len(docs))
        return httpx.Response(200)

    async with local_service(tmp_path, transport) as service:
        docs = [
            {**document(i), "doc_id": f"hist-team-2003-club-{i}", "category": "historical"}
            for i in range(101)
        ]
        async with service.sessions() as db:
            await service._queue_documents(db, docs, str(uuid4()))
            await db.commit()
        with pytest.raises(ServiceError, match="Historical"):
            await service.reconcile_index()
        assert not requests
        assert (await service.status())["index_sync"]["pending"] == 101
        service.settings.historical_index_enabled = True
        await service.reconcile_index()
        assert requests == [50, 50, 1]
        assert (await service.status())["index_sync"]["pending"] == 0


@pytest.mark.asyncio
async def test_legacy_cleanup_waits_for_replacement_and_retries_failed_delete(tmp_path):
    season = current_season()
    old, new = f"standings-{season}-mw05", f"standings-{season}"
    indexed, deletes = {old: {"old": True}}, []
    fail_upsert, fail_delete = True, True

    async def transport(request):
        if request.method == "DELETE":
            deletes.append(old)
            if fail_delete:
                return httpx.Response(503)
            indexed.pop(old, None)
        else:
            if fail_upsert:
                return httpx.Response(503)
            indexed.update({d["doc_id"]: d for d in json.loads(request.content)["documents"]})
        return httpx.Response(200)

    async with local_service(tmp_path, transport) as service:
        async with service.sessions() as db:
            db.add(
                IndexTask(
                    doc_id=old,
                    action="delete",
                    payload={"replacement_doc_id": new},
                    request_id=str(uuid4()),
                    updated_at=datetime.now(BANGKOK),
                )
            )
            await db.commit()
        await service.reconcile_index()
        assert old in indexed and not deletes
        async with service.sessions() as db:
            await service._queue_documents(
                db, [{**document(1), "category": "standings", "doc_id": new}], str(uuid4())
            )
            await db.commit()
        with pytest.raises(ServiceError):
            await service.reconcile_index()
        assert old in indexed and not deletes
        fail_upsert = False
        with pytest.raises(ServiceError):
            await service.reconcile_index()
        assert old in indexed and new in indexed
        assert (await service.status())["index_sync"]["pending"] == 1
        fail_delete = False
        await service.reconcile_index()
        assert set(indexed) == {new}
        assert deletes == [old, old]


@pytest.mark.asyncio
async def test_cancelled_jobs_finish_and_startup_recovers_orphans(tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'football.db'}"
    ingest_started = asyncio.Event()

    async def blocked_ingest(*_args):
        ingest_started.set()
        await asyncio.Event().wait()

    async def cancelled_report(*_args):
        raise asyncio.CancelledError

    async with local_service(tmp_path, lambda _request: httpx.Response(200)) as service:
        ingest_id = await service.start_job("ingest", "fixtures", "beat", str(uuid4()))
        service._ingest_primary = blocked_ingest
        ingest_task = asyncio.create_task(service.run_ingest(ingest_id, "fixtures", str(uuid4())))
        await asyncio.wait_for(ingest_started.wait(), timeout=2)
        ingest_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await ingest_task
        assert (await service.get_job(ingest_id))["status"] == "failed"

        report_id = await service.start_job("report", None, "beat", str(uuid4()))
        service._create_report = cancelled_report
        with pytest.raises(asyncio.CancelledError):
            await service.run_report(report_id, current_season(), 5, str(uuid4()))
        assert (await service.get_job(report_id))["status"] == "failed"

        queued_id = await service.start_job("ingest", "fixtures", "beat", str(uuid4()))
        running_id = await service.start_job("report", None, "beat", str(uuid4()))
        async with service.sessions() as db:
            running = await db.get(Job, running_id)
            running.status = "running"
            await db.commit()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200))
    ) as upstream:
        app = create_app(Settings(database_url=database_url), http=upstream)
        async with app.router.lifespan_context(app):
            restarted = app.state.service
            for old_id in (queued_id, running_id):
                recovered = await restarted.get_job(old_id)
                assert recovered["status"] == "failed"
                assert recovered["detail"] == "Interrupted by service restart"
            assert await restarted.start_job("ingest", "fixtures", "beat", str(uuid4()))
            assert await restarted.start_job("report", None, "beat", str(uuid4()))


@pytest.mark.asyncio
async def test_report_transition_ignores_unrelated_failed_outbox_task(tmp_path):
    indexed = {}

    async def transport(request):
        if request.method == "DELETE":
            indexed.pop(request.url.path.removeprefix("/index/"), None)
        else:
            indexed.update({doc["doc_id"]: doc for doc in json.loads(request.content)["documents"]})
        return httpx.Response(200)

    async with local_service(tmp_path, transport) as service:
        season = current_season()
        stale = report_payload(season, 4)
        stale.pop("search_text_en")
        stale["status"] = "published"
        async with service.sessions() as db:
            db.add(WeeklyReport(season=season, matchweek=4, status="published", payload=stale))
            db.add(
                WeeklyReport(
                    season=season, matchweek=5, status="draft", payload=report_payload(season, 5)
                )
            )
            db.add(
                IndexTask(
                    doc_id=f"weekly-{season}-mw04",
                    action="reconcile_report",
                    payload={"season": season, "matchweek": 4},
                    request_id=str(uuid4()),
                    updated_at=datetime.now(BANGKOK),
                )
            )
            await db.commit()

        published = await service.publish(season, 5, "beat", str(uuid4()))
        assert published["status"] == "published"
        assert f"weekly-{season}-mw05" in indexed
        unpublished = await service.unpublish(season, 5, "beat", str(uuid4()))
        assert unpublished["status"] == "unpublished"
        assert f"weekly-{season}-mw05" not in indexed

        async with service.sessions() as db:
            assert await db.get(IndexTask, f"weekly-{season}-mw04") is not None
            assert await db.get(IndexTask, f"weekly-{season}-mw05") is None
        with pytest.raises(ServiceError, match="Cannot backfill"):
            await service.reconcile_index()
