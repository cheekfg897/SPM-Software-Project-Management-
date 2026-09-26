"""Unit tests for migration 0015, which adds SCRUM-33's schema (ADR-0025).

It adds ``event_requests.programme_notes`` and ``.internal_planning_notes``, the
``field_changed`` event history kind and the ``significant_change`` notification
kind. ``flask db check`` doesn't compare enum members, so these tests check the
migration's value lists against the models and the earlier migrations they build on,
and render its SQL for Postgres offline so the upgrade and the downgrade are tested
without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_33

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0015_add_event_notes_and_change_kinds.py"
ASSIGNMENT_MIGRATION = "0010_add_coordinator_assignment_and_event_history.py"
REASSIGNMENT_MIGRATION = "0012_add_reassignment_history_kind.py"
NOTIFICATIONS_MIGRATION = "0009_create_notifications_table.py"
EQUIPMENT_MIGRATION = "0011_create_event_equipment_lines_table.py"


def test_the_previous_history_kinds_are_what_exists_after_migration_0012(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    after_0012 = set(load_migration(ASSIGNMENT_MIGRATION).HISTORY_KIND_VALUES) | set(
        load_migration(REASSIGNMENT_MIGRATION).ADDED_HISTORY_KIND_VALUES
    )

    assert set(migration.PREVIOUS_HISTORY_KIND_VALUES) == after_0012


def test_the_previous_notification_kinds_are_what_exists_after_migration_0011(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    after_0011 = (
        set(load_migration(NOTIFICATIONS_MIGRATION).KIND_VALUES)
        | set(load_migration(ASSIGNMENT_MIGRATION).ADDED_NOTIFICATION_KIND_VALUES)
        | set(load_migration(EQUIPMENT_MIGRATION).ADDED_KIND_VALUES)
    )

    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) == after_0011


def test_migration_and_model_agree_on_the_history_kinds(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)
    previous = set(migration.PREVIOUS_HISTORY_KIND_VALUES)
    added = set(migration.ADDED_HISTORY_KIND_VALUES)

    # Subset, not equality: a later migration could add a further history kind
    # this one doesn't know about, as 0011 and 0012 later did to 0009 and 0010.
    assert previous | added <= {kind.value for kind in EventHistoryKind}
    assert previous.isdisjoint(added)


def test_migration_and_model_agree_on_the_notification_kinds(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)
    previous = set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES)
    added = set(migration.ADDED_NOTIFICATION_KIND_VALUES)

    # Subset, not equality: a later migration could add a further notification kind
    # this one doesn't know about, as 0010 and 0011 later did to 0009.
    assert previous | added <= {kind.value for kind in NotificationKind}
    assert previous.isdisjoint(added)


def test_upgrade_adds_the_columns_then_both_kinds_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert "ALTER TABLE event_requests ADD COLUMN programme_notes TEXT" in sql
    assert "ALTER TABLE event_requests ADD COLUMN internal_planning_notes TEXT" in sql
    assert "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'field_changed'" in sql
    assert "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'significant_change'" in sql
    # Postgres won't let a transaction use an enum value it added, so both additions
    # sit between a COMMIT and a new BEGIN, after the columns are added.
    assert sql.index("ADD COLUMN") < sql.index("COMMIT") < sql.index("ADD VALUE")
    assert sql.index("ADD VALUE") < sql.index("BEGIN")


def test_downgrade_rebuilds_both_kinds_then_drops_the_columns(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'significant_change'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM "
        "('event_request_submitted', 'coordinator_assigned', 'equipment_requested')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "DELETE FROM event_history_entries WHERE kind = 'field_changed'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "CREATE TYPE event_history_entry_kind AS ENUM "
        "('coordinator_assigned', 'coordinator_reassigned')",
        "ALTER TABLE event_history_entries ALTER COLUMN kind "
        "TYPE event_history_entry_kind USING kind::text::event_history_entry_kind",
        "DROP TYPE event_history_entry_kind_old",
        "ALTER TABLE event_requests DROP COLUMN internal_planning_notes",
        "ALTER TABLE event_requests DROP COLUMN programme_notes",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
