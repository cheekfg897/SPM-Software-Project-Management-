"""Unit tests for migration 0006, which adds SCRUM-22's event request statuses.

``flask db check`` doesn't compare enum members, so these tests check the migration's
value list against the model. They also render the migration's SQL for Postgres
offline, so the upgrade and the downgrade are tested without a database (ADR-0012).
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventRequestStatus

pytestmark = pytest.mark.scrum_22

MIGRATION = "0006_add_event_request_statuses.py"

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]


def test_migration_and_model_agree_on_the_status_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)
    previous = set(migration.PREVIOUS_STATUS_VALUES)
    added = set(migration.ADDED_STATUS_VALUES)

    assert previous | added == {status.value for status in EventRequestStatus}
    assert previous.isdisjoint(added)


def test_upgrade_adds_each_new_value_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    for value in ["draft", "under_review", "confirmed", "completed", "cancelled", "rejected"]:
        assert f"ALTER TYPE event_request_status ADD VALUE '{value}'" in sql
    # Postgres won't let a transaction use an enum value it added, so the additions
    # sit between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index("ADD VALUE")
    assert sql.rindex("ADD VALUE") < sql.index("BEGIN")


def test_downgrade_rebuilds_the_type_with_only_submitted(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "UPDATE event_requests SET status = 'submitted' WHERE status != 'submitted'",
        "ALTER TYPE event_request_status RENAME TO event_request_status_old",
        "CREATE TYPE event_request_status AS ENUM ('submitted')",
        "ALTER TABLE event_requests ALTER COLUMN status "
        "TYPE event_request_status USING status::text::event_request_status",
        "DROP TYPE event_request_status_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
