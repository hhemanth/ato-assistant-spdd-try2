"""Repository module for the ``url_inventory`` table (FR-019)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, RepoBase


class UrlInventory(Base):
    """A discovered URL produced by a crawl run (per :mod:`data-model.md`)."""

    __tablename__ = "url_inventory"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        init=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id"), nullable=False
    )
    crawl_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    is_leaf: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    is_robots_disallowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    __table_args__ = (UniqueConstraint("url", name="uq_url_inventory_url"),)


class UrlInventoryRepo(RepoBase):
    """Typed CRUD + lookups for ``url_inventory``."""

    async def insert(
        self,
        *,
        url: str,
        discovered_at: datetime,
        crawl_run_id: uuid.UUID,
        crawl_depth: int,
        is_leaf: bool,
        user_agent: str,
        http_status: int | None = None,
        is_robots_disallowed: bool = False,
    ) -> UrlInventory:
        """Insert a single inventory row."""
        row = UrlInventory(
            url=url,
            discovered_at=discovered_at,
            crawl_run_id=crawl_run_id,
            crawl_depth=crawl_depth,
            is_leaf=is_leaf,
            user_agent=user_agent,
            http_status=http_status,
            is_robots_disallowed=is_robots_disallowed,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def find_by_url(self, url: str) -> UrlInventory | None:
        """Look up an inventory row by URL."""
        stmt = select(UrlInventory).where(UrlInventory.url == url)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_leaves_for_run(self, crawl_run_id: uuid.UUID) -> list[UrlInventory]:
        """Return every leaf URL discovered by a given run."""
        stmt = select(UrlInventory).where(
            UrlInventory.crawl_run_id == crawl_run_id,
            UrlInventory.is_leaf.is_(True),
            UrlInventory.is_robots_disallowed.is_(False),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
