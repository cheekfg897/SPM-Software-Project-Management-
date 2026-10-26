"""Unit tests for migration 0047, SCRUM-92's "replacement approved" notice (ADR-0108).

``notification_kind`` gains ``replacement_venue_approved``, the Organiser's notice that
a replacement venue was approved for an event a venue sent back (AC9, added 26 Oct).
``flask db check`` doesn't compare enum members, so these tests check the migration's
value lists against the model and the migrations below it, and render its SQL for
Postgres offline.

0047 revises 0046 (SCRUM-33), which adds ``safety_review_event_changed``.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_92

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0047_add_replacement_venue_approved.py"
#: The migration below this one, the last to change ``notification_kind`` before it.
MIGRATION_BELOW = "0046_add_safety_review_event_changed.py"
ADDED = "replacement_venue_approved"


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


def test_it_adds_the_models_new_kind_and_follows_0046(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.ADDED_NOTIFICATION_KIND_VALUES == (ADDED,)
    assert ADDED in {kind.value for kind in NotificationKind}
    assert ADDED not in migration.PREVIOUS_NOTIFICATION_KIND_VALUES
    assert migration.down_revision == "0046_add_safety_review_changed"
    # ``alembic_version`` holds at most 32 characters.
    assert migration.revision == "0047_add_replacement_approved"
    assert len(migration.revision) <= 32


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
        "DELETE FROM notifications WHERE kind = 'replacement_venue_approved'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'venue_booking_released', 'safety_review_event_changed')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert f"'{ADDED}')" not in sql
