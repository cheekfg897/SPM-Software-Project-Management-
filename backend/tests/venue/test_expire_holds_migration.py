"""Unit tests for migration 0037, SCRUM-94's expired holds.

It adds ``expired`` to ``booking_request_status``, a kind to
``event_history_entry_kind``, two to ``notification_kind`` and the column that records a
hold's warning. ``flask db check`` doesn't compare enum members, so these tests check
the migration's value lists against the models and the migrations below it, and render
its SQL for Postgres offline, so the upgrade and the downgrade are tested without a
database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.models import NotificationKind
from app.modules.venue.models import BookingRequestStatus

pytestmark = pytest.mark.scrum_94

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0037_expire_tentative_holds.py"
#: The last migration to change the request status and the notification kinds, and the
#: last to change the history kinds.
MIGRATION_BELOW = "0036_add_tentative_holds.py"
#: 0034 (SCRUM-85) is the last below this one to add a history kind; it adds a single
#: value, as ``ADDED_HISTORY_KIND_VALUE``.
HISTORY_MIGRATION_BELOW = "0034_add_equipment_preparation_details.py"


def _after(migration: ModuleType, values: str) -> set[str]:
    """The values a type has once ``migration`` has run: its previous and added ones."""
    previous = getattr(migration, f"PREVIOUS_{values}_VALUES")
    added = getattr(migration, f"ADDED_{values}_VALUES")
    return {*previous, *added}


def test_the_previous_values_are_what_exists_after_the_migrations_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(MIGRATION_BELOW)
    history_below = load_migration(HISTORY_MIGRATION_BELOW)

    assert set(migration.PREVIOUS_REQUEST_STATUS_VALUES) == _after(below, "REQUEST_STATUS")
    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) == _after(below, "NOTIFICATION_KIND")
    assert set(migration.PREVIOUS_HISTORY_KIND_VALUES) == {
        *history_below.PREVIOUS_HISTORY_KIND_VALUES,
        history_below.ADDED_HISTORY_KIND_VALUE,
    }


def test_the_migrations_value_lists_are_the_models_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert _after(migration, "REQUEST_STATUS") == {s.value for s in BookingRequestStatus}
    assert _after(migration, "NOTIFICATION_KIND") == {k.value for k in NotificationKind}
    assert _after(migration, "HISTORY_KIND") == {k.value for k in EventHistoryKind}


def test_the_revision_follows_0036_and_fits_alembics_version_column(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)

    assert migration.down_revision == "0036_add_tentative_holds"
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(migration.revision) <= 32


def test_upgrade_adds_the_column_then_the_enum_values_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "ALTER TABLE bookings ADD COLUMN hold_warning_sent_at TIMESTAMP WITH TIME ZONE",
        "COMMIT",
        "ALTER TYPE booking_request_status ADD VALUE IF NOT EXISTS 'expired'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'venue_hold_expired'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'venue_hold_expiring'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'venue_hold_expired'",
        "BEGIN",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_deletes_expired_requests_and_rebuilds_the_types(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    """An expired request is deleted, as 0036 deletes the On Hold ones.

    Putting it back On Hold could collide under the pending index with the request
    raised again for the same slot after it expired (SCRUM-94 AC2). The pending index is
    dropped around the request rebuild, as in 0036.
    """
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM venue_booking_requests WHERE status = 'expired'",
        "DELETE FROM event_history_entries WHERE kind = 'venue_hold_expired'",
        "DELETE FROM notifications WHERE kind = 'venue_hold_expiring'",
        "DELETE FROM notifications WHERE kind = 'venue_hold_expired'",
        "ALTER TABLE bookings DROP COLUMN hold_warning_sent_at",
        "DROP INDEX uq_venue_booking_requests_pending",
        "ALTER TYPE booking_request_status RENAME TO booking_request_status_old",
        "CREATE TYPE booking_request_status AS ENUM ('pending', 'withdrawn', 'approved', "
        "'rejected', 'conflicting', 'on_hold')",
        "DROP TYPE booking_request_status_old",
        # Back to the index 0036 left, Conflicting and On Hold included.
        "CREATE UNIQUE INDEX uq_venue_booking_requests_pending ON venue_booking_requests "
        "(event_id, venue_id, starts_at, ends_at) "
        "WHERE status IN ('pending', 'conflicting', 'on_hold')",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "DROP TYPE event_history_entry_kind_old",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
