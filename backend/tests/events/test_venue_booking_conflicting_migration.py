"""Unit tests for migration 0041, SCRUM-50's Conflicting booking notice (ADR-0055).

``notification_kind`` gains ``venue_booking_conflicting`` (AC6). ``flask db check``
doesn't compare enum members, so these tests check the migration's value lists against
the model and the migration below it, and render its SQL for Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_50

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
AssertMigrationAndModelAgree = Callable[[tuple[str, ...], tuple[str, ...], set[str]], None]

MIGRATION = "0041_add_venue_booking_conflicting.py"
#: The last migration to change ``notification_kind``.
MIGRATION_BELOW = "0039_flag_alternative_venues.py"
ADDED = "venue_booking_conflicting"


def test_the_previous_values_are_what_the_migration_below_left(
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


def test_migration_and_model_agree_and_it_follows_the_alternative_venue_migration(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        migration.ADDED_NOTIFICATION_KIND_VALUES,
        {kind.value for kind in NotificationKind},
    )
    assert migration.ADDED_NOTIFICATION_KIND_VALUES == (ADDED,)
    assert migration.down_revision == "0039_flag_alternative_venues"
    # ``alembic_version`` holds at most 32 characters.
    assert migration.revision == "0041_add_booking_conflicting"


def test_upgrade_adds_the_value_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    add_value = f"ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS '{ADDED}'"
    # Postgres won't let a transaction use an enum value it added, so the addition sits
    # between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index(add_value) < sql.index("BEGIN")


def test_downgrade_deletes_the_new_rows_and_rebuilds_the_type_without_them(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'venue_booking_conflicting'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'venue_hold_expired', 'alternative_venue_needed')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert f"'{ADDED}')" not in sql
