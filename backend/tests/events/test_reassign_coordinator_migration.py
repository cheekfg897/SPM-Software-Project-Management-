"""Unit tests for migration 0012, which adds SCRUM-87's history kind (ADR-0021).

``event_history_entry_kind`` gains ``coordinator_reassigned``; ``notification_kind``
is left alone, since a reassignment only tells the new coordinator, with the existing
``coordinator_assigned``. ``flask db check`` doesn't compare enum members, so these
tests check the migration's value lists against the model and migration 0010, and
render its SQL for Postgres offline so the upgrade and the downgrade are tested
without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind

pytestmark = pytest.mark.scrum_87

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0012_add_reassignment_history_kind.py"
#: Migration 0010 created ``event_history_entry_kind``.
ASSIGNMENT_MIGRATION = "0010_add_coordinator_assignment_and_event_history.py"


def test_migration_and_model_agree_on_the_history_kinds(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)
    created_by_0010 = set(load_migration(ASSIGNMENT_MIGRATION).HISTORY_KIND_VALUES)
    previous = set(migration.PREVIOUS_HISTORY_KIND_VALUES)
    added = set(migration.ADDED_HISTORY_KIND_VALUES)

    assert previous == created_by_0010
    assert previous | added == {kind.value for kind in EventHistoryKind}
    assert previous.isdisjoint(added)


def test_upgrade_adds_the_history_kind_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    history_kind = (
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'coordinator_reassigned'"
    )
    # Postgres won't let a transaction use an enum value it added, so the addition sits
    # between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index(history_kind) < sql.index("BEGIN")
    assert "notification_kind" not in sql


def test_downgrade_deletes_the_new_entries_and_rebuilds_the_type_without_the_new_kind(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM event_history_entries WHERE kind = 'coordinator_reassigned'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "CREATE TYPE event_history_entry_kind AS ENUM ('coordinator_assigned')",
        "ALTER TABLE event_history_entries ALTER COLUMN kind "
        "TYPE event_history_entry_kind USING kind::text::event_history_entry_kind",
        "DROP TYPE event_history_entry_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "notification_kind" not in sql
