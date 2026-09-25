"""Unit tests for migration 0013, which indexes event requests by proposed date.

SCRUM-38's list of the equipment awaiting Technical Support keeps only events from
today on (ADR-0022), so it filters and sorts on ``event_requests.proposed_date``. The
migration's SQL is rendered for Postgres offline, so the upgrade and the downgrade are
tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventRequest

pytestmark = pytest.mark.scrum_38

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]

MIGRATION = "0013_add_event_requests_proposed_date_index.py"
INDEX_NAME = "ix_event_requests_proposed_date"


def test_the_model_declares_the_index_the_migration_creates() -> None:
    index_names = {index.name for index in EventRequest.__table__.indexes}

    assert INDEX_NAME in index_names


def test_upgrade_creates_the_index(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert f"CREATE INDEX {INDEX_NAME} ON event_requests (proposed_date)" in sql


def test_downgrade_drops_the_index(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.downgrade)

    assert f"DROP INDEX {INDEX_NAME}" in sql
