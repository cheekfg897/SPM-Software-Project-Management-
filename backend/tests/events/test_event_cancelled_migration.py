"""Unit tests for migration 0052, SCRUM-61's cancelled event (ADR-0122).

``notification_kind`` gains ``event_cancelled``, the notice the assigned coordinator
(AC1) and every registered Attendee (AC4) get, and
``venue_booking_released_by_cancellation``, Venue Staff's notice of each booking or hold
released (AC8). ``event_history_entry_kind`` gains ``event_cancelled``, the entry that
keeps who cancelled the event and why (AC1). ``flask db check`` doesn't compare enum
members, so these tests check the migration's value lists against the models and the
migration below it, and render its SQL for Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_61

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0052_add_event_cancelled.py"
#: The last migration to change either type before this one.
KINDS_BELOW = "0051_add_booking_cancelled.py"


def _model_values(enum_type: type) -> set[str]:
    return {member.value for member in enum_type}


def test_it_follows_the_booking_cancelled_migration(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.down_revision == "0051_add_booking_cancelled"
    assert migration.revision == "0052_add_event_cancelled"
    # ``alembic_version`` holds at most 32 characters.
    assert len(migration.revision) <= 32


def test_the_previous_values_are_what_the_migration_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(KINDS_BELOW)

    # In Postgres's order: each ADD VALUE appends.
    notifications_left = (
        *below.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *below.ADDED_NOTIFICATION_KIND_VALUES,
    )
    history_left = (*below.PREVIOUS_HISTORY_KIND_VALUES, *below.ADDED_HISTORY_KIND_VALUES)

    assert notifications_left == migration.PREVIOUS_NOTIFICATION_KIND_VALUES
    assert history_left == migration.PREVIOUS_HISTORY_KIND_VALUES


def test_it_adds_the_cancellation_kinds(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.ADDED_NOTIFICATION_KIND_VALUES == (
        "event_cancelled",
        "venue_booking_released_by_cancellation",
    )
    assert migration.ADDED_HISTORY_KIND_VALUES == ("event_cancelled",)


def test_with_the_values_added_each_type_holds_exactly_the_models_values(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    notification_kinds = {
        *migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *migration.ADDED_NOTIFICATION_KIND_VALUES,
    }
    history_kinds = {*migration.PREVIOUS_HISTORY_KIND_VALUES, *migration.ADDED_HISTORY_KIND_VALUES}

    assert notification_kinds == _model_values(NotificationKind)
    assert history_kinds == _model_values(EventHistoryKind)


def test_upgrade_adds_every_value_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    # Postgres won't let a transaction use an enum value it added, so the additions sit
    # between a COMMIT and a new BEGIN.
    expected_in_order = [
        "COMMIT",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'event_cancelled'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS "
        "'venue_booking_released_by_cancellation'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'event_cancelled'",
        "BEGIN",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_removes_the_new_rows_and_rebuilds_each_type_without_them(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'event_cancelled'",
        "DELETE FROM notifications WHERE kind = 'venue_booking_released_by_cancellation'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'venue_booking_cancelled', 'safety_review_venue_cancelled')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "DELETE FROM event_history_entries WHERE kind = 'event_cancelled'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "CREATE TYPE event_history_entry_kind AS ENUM ('coordinator_assigned'",
        "'venue_booking_reconfirmed', 'venue_booking_cancelled')",
        "ALTER TABLE event_history_entries ALTER COLUMN kind "
        "TYPE event_history_entry_kind USING kind::text::event_history_entry_kind",
        "DROP TYPE event_history_entry_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "'event_cancelled')" not in sql
