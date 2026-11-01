"""Unit tests for SCRUM-62's registration notification kinds and migration 0050.

AC4: the Event Organiser is told when an Attendee registers or withdraws. AC5: the
Attendee is told when their own registration is confirmed or withdrawn. Each has its own
kind and message (ADR-0125). ``flask db check`` doesn't compare enum members, so the
migration's value lists are checked against the model and the migration below it, and
its SQL is rendered for Postgres offline.

0050 revises 0049 (SCRUM-59), which adds ``venue_booking_reconfirmed``. Other open
branches plan an 0050 too, so whichever merges second is re-chained (ADR-0125).
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_62

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0050_add_registration_notification_kinds.py"
#: The last migration to change ``notification_kind`` before this one.
MIGRATION_BELOW = "0049_add_venue_booking_reconfirmed.py"
ADDED = (
    "registration_confirmed",
    "registration_withdrawn",
    "attendee_registered",
    "attendee_withdrawn",
)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("registration_confirmed", "Your registration for this event is confirmed."),
        ("registration_withdrawn", "Your registration for this event has been withdrawn."),
        ("attendee_registered", "An Attendee registered for your event."),
        ("attendee_withdrawn", "An Attendee withdrew from your event."),
    ],
)
def test_each_registration_notice_says_what_happened(value: str, message: str) -> None:
    assert MESSAGE_BY_KIND[NotificationKind(value)] == message


def test_the_previous_values_are_what_the_migrations_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(MIGRATION_BELOW)
    # In Postgres's order: each ADD VALUE appends.
    left_below = (
        *below.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *below.ADDED_NOTIFICATION_KIND_VALUES,
    )

    assert left_below == migration.PREVIOUS_NOTIFICATION_KIND_VALUES


def test_it_adds_the_models_new_kinds_and_follows_0049(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.ADDED_NOTIFICATION_KIND_VALUES == ADDED
    assert set(ADDED) <= {kind.value for kind in NotificationKind}
    assert set(ADDED).isdisjoint(migration.PREVIOUS_NOTIFICATION_KIND_VALUES)
    assert migration.down_revision == "0049_add_booking_reconfirmed"
    # ``alembic_version`` holds at most 32 characters.
    assert migration.revision == "0050_add_registration_notices"
    assert len(migration.revision) <= 32


def test_upgrade_adds_each_value_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    # Postgres won't let a transaction use an enum value it added, so the additions sit
    # between a COMMIT and a new BEGIN.
    for value in ADDED:
        add_value = f"ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS '{value}'"
        assert sql.index("COMMIT") < sql.index(add_value) < sql.index("BEGIN")


def test_downgrade_deletes_the_new_rows_and_rebuilds_the_type_without_them(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'registration_confirmed'",
        "DELETE FROM notifications WHERE kind = 'attendee_withdrawn'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'replacement_venue_approved', 'venue_booking_reconfirmed')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    for value in ADDED:
        assert f"'{value}')" not in sql
