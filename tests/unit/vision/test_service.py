from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from resham.vision import service
from resham.vision.classifier import VisionClassification


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


def _fake_product(**overrides):
    defaults = dict(
        id="p1",
        primary_image_url="https://example.com/a.jpg",
        vision_category=None,
        vision_colors=[],
        vision_classified_at=None,
        embedded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_classify_incremental_sets_vision_fields_on_success(monkeypatch):
    row = _fake_product()
    session = _FakeSession([row])

    async def fake_classify(image_url, **kwargs):
        assert image_url == "https://example.com/a.jpg"
        return VisionClassification(category="kurta", colors=["red"])

    monkeypatch.setattr(service, "classify_product_image", fake_classify)
    monkeypatch.setattr(
        service, "get_settings",
        lambda: SimpleNamespace(
            vision_classification_batch_size=50,
            gemini_api_key="k", gemini_vision_model="m", gemini_vision_timeout_seconds=8.0,
        ),
    )

    stats = await service.classify_incremental(session)

    assert stats == {"classified": 1, "failed": 0}
    assert row.vision_category == "kurta"
    assert row.vision_colors == ["red"]
    assert row.vision_classified_at is not None
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_classify_incremental_resets_embedded_at_so_the_new_terms_reach_the_vector(monkeypatch):
    row = _fake_product(embedded_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    session = _FakeSession([row])

    async def fake_classify(image_url, **kwargs):
        return VisionClassification(category="kurta", colors=[])

    monkeypatch.setattr(service, "classify_product_image", fake_classify)
    monkeypatch.setattr(
        service, "get_settings",
        lambda: SimpleNamespace(
            vision_classification_batch_size=50,
            gemini_api_key="k", gemini_vision_model="m", gemini_vision_timeout_seconds=8.0,
        ),
    )

    await service.classify_incremental(session)

    assert row.embedded_at is None


@pytest.mark.asyncio
async def test_classify_incremental_leaves_embedded_at_untouched_when_nothing_was_identified(monkeypatch):
    row = _fake_product(embedded_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    session = _FakeSession([row])

    async def fake_classify(image_url, **kwargs):
        return VisionClassification(category=None, colors=[])

    monkeypatch.setattr(service, "classify_product_image", fake_classify)
    monkeypatch.setattr(
        service, "get_settings",
        lambda: SimpleNamespace(
            vision_classification_batch_size=50,
            gemini_api_key="k", gemini_vision_model="m", gemini_vision_timeout_seconds=8.0,
        ),
    )

    await service.classify_incremental(session)

    assert row.embedded_at is not None
    assert row.vision_classified_at is not None


@pytest.mark.asyncio
async def test_classify_incremental_leaves_a_failed_row_unclassified_for_retry(monkeypatch):
    row = _fake_product()
    session = _FakeSession([row])

    async def fake_classify(image_url, **kwargs):
        return None

    monkeypatch.setattr(service, "classify_product_image", fake_classify)
    monkeypatch.setattr(
        service, "get_settings",
        lambda: SimpleNamespace(
            vision_classification_batch_size=50,
            gemini_api_key="k", gemini_vision_model="m", gemini_vision_timeout_seconds=8.0,
        ),
    )

    stats = await service.classify_incremental(session)

    assert stats == {"classified": 0, "failed": 1}
    assert row.vision_classified_at is None
    assert row.embedded_at is not None


@pytest.mark.asyncio
async def test_classify_incremental_respects_an_explicit_limit_override(monkeypatch):
    rows = [_fake_product(id=f"p{i}") for i in range(3)]
    session = _FakeSession(rows)
    seen_limits = []

    class _CapturingResult(_FakeResult):
        pass

    async def fake_execute(stmt):
        # The batch limit is baked into the SQLAlchemy statement itself
        # (select(...).limit(n)); assert on the compiled LIMIT clause
        # rather than trying to intercept the ORM call directly.
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        seen_limits.append(compiled)
        return _FakeResult(rows)

    session.execute = fake_execute

    async def fake_classify(image_url, **kwargs):
        return VisionClassification(category="kurta", colors=[])

    monkeypatch.setattr(service, "classify_product_image", fake_classify)
    monkeypatch.setattr(
        service, "get_settings",
        lambda: SimpleNamespace(
            vision_classification_batch_size=50,
            gemini_api_key="k", gemini_vision_model="m", gemini_vision_timeout_seconds=8.0,
        ),
    )

    await service.classify_incremental(session, limit=1)

    assert "LIMIT 1" in seen_limits[0]
