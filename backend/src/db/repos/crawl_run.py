"""Repository module for the ``crawl_run`` table (FR-019, FR-020)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Integer,
    Numeric,
    String,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase


class CrawlRun(Base):
    """One execution of the leaf-URL crawler (per :mod:`data-model.md`)."""

    __tablename__ = "crawl_run"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    seed_urls: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    depth_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_limit_qps: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    pages_visited: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    pages_skipped_by_robots: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    pages_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )


class CrawlRunRepo(RepoBase):
    """Typed CRUD + summary updates for ``crawl_run``."""

    async def start(
        self,
        *,
        started_at: datetime,
        seed_urls: list[str],
        depth_cap: int,
        rate_limit_qps: Decimal,
    ) -> CrawlRun:
        """Insert a new in-flight crawl-run row."""
        row = CrawlRun(
            started_at=started_at,
            seed_urls=list(seed_urls),
            depth_cap=depth_cap,
            rate_limit_qps=rate_limit_qps,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, crawl_run_id: uuid.UUID) -> CrawlRun | None:
        """Look up a crawl run by primary key."""
        stmt = select(CrawlRun).where(CrawlRun.id == crawl_run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def finalize(
        self,
        crawl_run_id: uuid.UUID,
        *,
        finished_at: datetime,
        pages_visited: int,
        pages_skipped_by_robots: int,
        pages_failed: int,
    ) -> None:
        """Record final counters when a crawl run ends."""
        stmt = (
            update(CrawlRun)
            .where(CrawlRun.id == crawl_run_id)
            .values(
                finished_at=finished_at,
                pages_visited=pages_visited,
                pages_skipped_by_robots=pages_skipped_by_robots,
                pages_failed=pages_failed,
            )
        )
        await self.session.execute(stmt)
