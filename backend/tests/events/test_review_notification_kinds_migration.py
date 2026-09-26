"""Unit tests for migration 0019, which adds SCRUM-39's notification kind (ADR-0030).

``notification_kind`` gains ``request_assigned``, the organiser's notice that an Event
Coordinator has been assigned to their request (AC1); ``event_history_entry_kind`` is
left alone. ``flask db check`` doesn't compare enum members, so these tests check the
migration's value lists against the model and the migration below it, and render its
SQL for Postgres offline so the upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_39

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0019_add_review_notification_kinds.py"
#: The last migration to change ``notification_kind`` before this one.
PREVIOUS_MIGRATION = "0018_add_clarification_status_and_kinds.py"


def test_the_previous_notification_kinds_are_what_exists_after_the_migration_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(PREVIOUS_MIGRATION)
    after_below = set(below.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(
        below.ADDED_NOTIFICATION_KIND_VALUES
    )

    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) == after_below


def test_migration_and_model_agree_on_the_notification_kinds(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)
    previous = set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES)
    added = set(migration.ADDED_NOTIFICATION_KIND_VALUES)

    # Subset, not equality: a later migration could add a further notification kind
    # this one doesn't know about, as this one does to the migrations below it.
    assert previous | added <= {kind.value for kind in NotificationKind}
    assert previous.isdisjoint(added)
    assert added == {"request_assigned"}


def test_upgrade_adds_the_kind_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    request_assigned = "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'request_assigned'"
    # Postgres won't let a transaction use an enum value it added, so the addition sits
    # between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index(request_assigned) < sql.index("BEGIN")
    assert "event_history_entry_kind" not in sql


def test_downgrade_deletes_the_new_notifications_and_rebuilds_the_type_without_the_new_kind(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'request_assigned'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted', "
        "'coordinator_assigned', 'equipment_requested', 'significant_change', "
        "'event_request_approved', 'event_request_rejected', 'clarification_requested', "
        "'clarification_answered')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "event_history_entry_kind" not in sql
