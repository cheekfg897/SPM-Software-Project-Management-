"""Unit tests for migration 0010, which adds SCRUM-30's schema (ADR-0018).

It adds the ``coordinator_assigned`` notification kind, the
``event_requests.coordinator_id`` column and the ``event_history_entries`` table.
``flask db check`` doesn't compare enum members, so these tests check the migration's
value lists against the models, and render its SQL for Postgres offline so the
upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_30

MIGRATION = "0010_add_coordinator_assignment_and_event_history.py"

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]


def test_migration_and_models_agree_on_the_kind_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)
    created_by_0009 = set(load_migration("0009_create_notifications_table.py").KIND_VALUES)
    previous = set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES)
    added = set(migration.ADDED_NOTIFICATION_KIND_VALUES)

    assert previous == created_by_0009
    # Migration 0011 adds a kind of its own, so the model has these and more.
    assert added.issubset({kind.value for kind in NotificationKind})
    assert previous.isdisjoint(added)
    assert set(migration.HISTORY_KIND_VALUES) == {kind.value for kind in EventHistoryKind}


def test_upgrade_adds_the_kind_outside_the_transaction_then_the_column_and_the_table(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    # Postgres won't let a transaction use an enum value it added, so the addition
    # sits between a COMMIT and a new BEGIN, before anything else.
    assert "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'coordinator_assigned'" in sql
    assert sql.index("COMMIT") < sql.index("ADD VALUE") < sql.index("BEGIN")
    assert_in_order(
        sql[sql.index("BEGIN") :],
        [
            "ALTER TABLE event_requests ADD COLUMN coordinator_id INTEGER",
            "CREATE INDEX ix_event_requests_coordinator_id ON event_requests (coordinator_id)",
            "CREATE TYPE event_history_entry_kind AS ENUM ('coordinator_assigned')",
            "CREATE TABLE event_history_entries",
            "CREATE INDEX ix_event_history_entries_event_request_id "
            "ON event_history_entries (event_request_id)",
        ],
    )


def test_downgrade_removes_the_table_the_column_and_rebuilds_the_notification_kind(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(
        sql,
        [
            "DROP TABLE event_history_entries",
            "DROP TYPE event_history_entry_kind",
            "ALTER TABLE event_requests DROP COLUMN coordinator_id",
            "DELETE FROM notifications WHERE kind = 'coordinator_assigned'",
            "ALTER TYPE notification_kind RENAME TO notification_kind_old",
            "CREATE TYPE notification_kind AS ENUM ('event_request_submitted')",
            "ALTER TABLE notifications ALTER COLUMN kind "
            "TYPE notification_kind USING kind::text::notification_kind",
            "DROP TYPE notification_kind_old",
        ],
    )
