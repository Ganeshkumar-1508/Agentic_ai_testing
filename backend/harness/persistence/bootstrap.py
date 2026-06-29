"""Schema bootstrap — pre-production: create_all + alembic stamp.

No legacy/data-migration concerns since we're not live yet.
"""

from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncEngine

from harness.persistence.base import Base

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = __file__.rsplit("/", 1)[0] + "/migrations"


def _alembic_config(sqlalchemy_url: str) -> AlembicConfig:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)
    return cfg


async def bootstrap_schema(engine: AsyncEngine, sqlalchemy_url: str) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Schema: create_all complete")

    cfg = _alembic_config(sqlalchemy_url)
    command.stamp(cfg, "head")
    logger.info("Schema: stamped alembic head")
