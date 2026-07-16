from types import SimpleNamespace
from uuid import uuid4

import pytest
from resham.worker import main


class _SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _SessionMaker:
    def __call__(self):
        return _SessionContext()


class _FakeScheduler:
    def __init__(self):
        self.calls = []

    def add_job(self, func, trigger, **kwargs):
        self.calls.append((func, trigger, kwargs))


@pytest.mark.asyncio
async def test_run_cycle_crawls_then_indexes(monkeypatch):
    crawl_run_id = uuid4()

    async def fake_crawl_all(session_maker, *, trigger, brand_slugs=None):
        assert isinstance(session_maker, _SessionMaker)
        assert trigger == "manual"
        assert brand_slugs == ["zellbury"]
        return crawl_run_id

    async def fake_index_incremental(session, collection):
        assert collection == "collection"
        return {"embedded": 4, "metadata_synced": 7}

    async def fake_classify_incremental(session):
        return {"classified": 2, "failed": 1}

    monkeypatch.setattr(main, "get_session_maker", lambda: _SessionMaker())
    monkeypatch.setattr(main, "crawl_all", fake_crawl_all)
    monkeypatch.setattr(main, "get_collection", lambda: "collection")
    monkeypatch.setattr(main, "index_incremental", fake_index_incremental)
    monkeypatch.setattr(main, "classify_incremental", fake_classify_incremental)

    result = await main.run_cycle(trigger="manual", brand_slugs=["zellbury"])

    assert result == {
        "crawl_run_id": str(crawl_run_id),
        "trigger": "manual",
        "brands": ["zellbury"],
        "indexing": {"embedded": 4, "metadata_synced": 7},
        "vision": {"classified": 2, "failed": 1},
    }


@pytest.mark.asyncio
async def test_scheduled_cycle_swallows_exceptions(monkeypatch, caplog):
    async def fake_run_cycle(*, trigger, brand_slugs=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "run_cycle", fake_run_cycle)

    with caplog.at_level("ERROR"):
        await main.scheduled_cycle()

    assert "Scheduled crawl/index cycle failed" in caplog.text


def test_schedule_worker_jobs_uses_interval_seconds():
    scheduler = _FakeScheduler()
    settings = SimpleNamespace(crawl_interval_hours=1.5)

    main.schedule_worker_jobs(scheduler, settings)

    assert len(scheduler.calls) == 1
    func, trigger, kwargs = scheduler.calls[0]
    assert func is main.scheduled_cycle
    assert trigger == "interval"
    assert kwargs["seconds"] == 5400
    assert kwargs["id"] == "crawl_and_index"
    assert kwargs["max_instances"] == 1
    assert kwargs["coalesce"] is True


def test_parse_args_rejects_brand_without_once():
    with pytest.raises(SystemExit):
        main.parse_args(["--brand", "zellbury"])
