"""Unit tests for migration 0049, SCRUM-59's reconfirmation kinds (ADR-0112).

``notification_kind`` gains ``venue_booking_reconfirmed``, the coordinator's notice
that Venue Staff reconfirmed a flagged booking (AC2), and ``event_history_entry_kind``
gains the same value, the entry that records it. ``flask db check`` doesn't compare enum
members, so these tests check the migration's value lists against the models and the
migrations below it, and render its SQL for Postgres offline.

0049 revises 0048 (PR #149, SCRUM-89), which changes neither type.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_59

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0049_add_venue_booking_reconfirmed.py"
#: The last migrations to change each type before this one.
NOTIFICATION_KIND_BELOW = "0047_add_replacement_venue_approved.py"
HISTORY_KIND_BELOW = "0039_flag_alternative_venues.py"
ADDED = "venue_booking_reconfirmed"


def test_the_previous_notification_kinds_are_what_the_migrations_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(NOTIFICATION_KIND_BELOW)
    # In Postgres's order: each ADD VALUE appends.
    left_below = (
        *below.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *below.ADDED_NOTIFICATION_KIND_VALUES,
    )

    assert left_below == migration.PREVIOUS_NOTIFICATION_KIND_VALUES


def test_the_previous_history_kinds_are_what_the_migrations_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(HISTORY_KIND_BELOW)
    left_below = (*below.PREVIOUS_HISTORY_KIND_VALUES, *below.ADDED_HISTORY_KIND_VALUES)

    assert left_below == migration.PREVIOUS_HISTORY_KIND_VALUES


def test_it_adds_the_models_new_kinds_and_follows_0048(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.ADDED_NOTIFICATION_KIND_VALUES == (ADDED,)
    assert migration.ADDED_HISTORY_KIND_VALUES == (ADDED,)
    assert ADDED in {kind.value for kind in NotificationKind}
    assert ADDED in {kind.value for kind in EventHistoryKind}
    assert ADDED not in migration.PREVIOUS_NOTIFICATION_KIND_VALUES
    assert ADDED not in migration.PREVIOUS_HISTORY_KIND_VALUES
    assert migration.down_revision == "0048_create_revoked_tokens"
    # ``alembic_version`` holds at most 32 characters.
    assert migration.revision == "0049_add_booking_reconfirmed"
    assert len(migration.revision) <= 32


def test_with_the_values_added_each_type_holds_only_the_models_values(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    notification_kinds = {
        *migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *migration.ADDED_NOTIFICATION_KIND_VALUES,
    }
    history_kinds = {*migration.PREVIOUS_HISTORY_KIND_VALUES, *migration.ADDED_HISTORY_KIND_VALUES}

    # Subset, not equality: a later migration (0051 SCRUM-111) adds further kinds.
    assert notification_kinds <= {kind.value for kind in NotificationKind}
    assert history_kinds <= {kind.value for kind in EventHistoryKind}


def test_upgrade_adds_both_values_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    add_notification = f"ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS '{ADDED}'"
    add_history = f"ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS '{ADDED}'"
    # Postgres won't let a transaction use an enum value it added, so the additions sit
    # between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index(add_notification) < sql.index("BEGIN")
    assert sql.index("COMMIT") < sql.index(add_history) < sql.index("BEGIN")


def test_downgrade_deletes_the_new_rows_and_rebuilds_both_types_without_them(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'venue_booking_reconfirmed'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'safety_review_event_changed', 'replacement_venue_approved')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "DELETE FROM event_history_entries WHERE kind = 'venue_booking_reconfirmed'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "CREATE TYPE event_history_entry_kind AS ENUM ('coordinator_assigned'",
        "'alternative_venue_needed', 'safety_approval_withdrawn')",
        "ALTER TABLE event_history_entries ALTER COLUMN kind "
        "TYPE event_history_entry_kind USING kind::text::event_history_entry_kind",
        "DROP TYPE event_history_entry_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert f"'{ADDED}')" not in sql
