"""Unit tests for migration 0032, SCRUM-98's history and notification kinds (ADR-0047).

``event_history_entry_kind`` gains ``safety_outcome_recorded`` (AC7) and
``notification_kind`` the three outcome notices (AC8). ``flask db check`` doesn't
compare enum members, so these tests check the migration's value lists against the
models and the migrations below it, and render its SQL for Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_98

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
AssertMigrationAndModelAgree = Callable[[tuple[str, ...], tuple[str, ...], set[str]], None]

MIGRATION = "0032_add_safety_outcome.py"
#: The last migrations to change each type before this one.
PREVIOUS_HISTORY_MIGRATION = "0029_add_safety_review.py"
PREVIOUS_NOTIFICATION_MIGRATION = "0030_add_safety_review_notification_kind.py"
ADDED_NOTIFICATIONS = ("safety_check_approved", "safety_check_rejected", "safety_changes_requested")


def test_the_previous_values_are_what_the_migrations_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    history_below = load_migration(PREVIOUS_HISTORY_MIGRATION)
    notification_below = load_migration(PREVIOUS_NOTIFICATION_MIGRATION)
    # In Postgres's order: each ADD VALUE appends.
    history_left = (
        *history_below.PREVIOUS_HISTORY_KIND_VALUES,
        *history_below.ADDED_HISTORY_KIND_VALUES,
    )
    notifications_left = (
        *notification_below.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *notification_below.ADDED_NOTIFICATION_KIND_VALUES,
    )

    assert history_left == migration.PREVIOUS_HISTORY_KIND_VALUES
    assert notifications_left == migration.PREVIOUS_NOTIFICATION_KIND_VALUES


def test_migration_and_models_agree_and_it_follows_the_notification_migration(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_HISTORY_KIND_VALUES,
        migration.ADDED_HISTORY_KIND_VALUES,
        {kind.value for kind in EventHistoryKind},
    )
    assert_migration_and_model_agree(
        migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        migration.ADDED_NOTIFICATION_KIND_VALUES,
        {kind.value for kind in NotificationKind},
    )
    assert migration.ADDED_HISTORY_KIND_VALUES == ("safety_outcome_recorded",)
    assert migration.ADDED_NOTIFICATION_KIND_VALUES == ADDED_NOTIFICATIONS
    assert migration.down_revision == "0030_add_safety_review_kind"


def test_upgrade_adds_the_values_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    add_history = (
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'safety_outcome_recorded'"
    )
    add_last_notification = (
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'safety_changes_requested'"
    )
    # Postgres won't let a transaction use an enum value it added, so the additions sit
    # between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index(add_history) < sql.index(add_last_notification)
    assert sql.index(add_last_notification) < sql.index("BEGIN")


def test_downgrade_deletes_the_new_rows_and_rebuilds_each_type_without_them(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'safety_check_approved'",
        "DELETE FROM notifications WHERE kind = 'safety_changes_requested'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "DELETE FROM event_history_entries WHERE kind = 'safety_outcome_recorded'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "ALTER TABLE event_history_entries ALTER COLUMN kind "
        "TYPE event_history_entry_kind USING kind::text::event_history_entry_kind",
        "DROP TYPE event_history_entry_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "'safety_check_approved')" not in sql
