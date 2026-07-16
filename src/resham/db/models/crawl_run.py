"""Crawl run models — per-cycle and per-brand crawl status, making failures
visible and debuggable instead of silently falling back to stale data."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from resham.db.base import Base


class CrawlRun(Base):
    """One row per full crawl cycle across all active brands."""

    __tablename__ = "crawl_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # running | success | partial_failure | failed
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    # scheduled | manual
    trigger: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class CrawlRunBrand(Base):
    """Per-brand result within one crawl_run — isolates one broken brand's
    failure from the other 24."""

    __tablename__ = "crawl_run_brands"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    crawl_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    # success | failed | skipped
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)

    products_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products_mapped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products_upserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products_unchanged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products_removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
