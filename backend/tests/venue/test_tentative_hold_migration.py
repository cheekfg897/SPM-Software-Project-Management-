"""Unit tests for migration 0036, SCRUM-75's tentative holds.

It adds ``on_hold`` to ``booking_request_status``, two kinds to ``notification_kind``
and the columns a hold needs. ``flask db check`` doesn't compare enum members, so these
tests check the migration's value lists against the models and render its SQL for
Postgres offline, so the upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.notifications.models import NotificationKind
from app.modules.venue.models import BookingRequestStatus

pytestmark = pytest.mark.scrum_75

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0036_add_tentative_holds.py"
#: The migration that left ``booking_request_status`` as it was before this one.
REQUEST_STATUS_MIGRATION_BELOW = "0028_add_conflicting_status.py"


def test_the_previous_request_statuses_are_what_exists_after_the_migration_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(REQUEST_STATUS_MIGRATION_BELOW)
    after_below = {*below.PREVIOUS_REQUEST_STATUS_VALUES, "conflicting"}

    assert set(migration.PREVIOUS_REQUEST_STATUS_VALUES) == after_below


def test_the_migrations_value_lists_are_the_models_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    request_values = {
        *migration.PREVIOUS_REQUEST_STATUS_VALUES,
        *migration.ADDED_REQUEST_STATUS_VALUES,
    }
    notification_values = {
        *migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *migration.ADDED_NOTIFICATION_KIND_VALUES,
    }
    # Subset, not equality: 0037 (SCRUM-94) adds further values this one doesn't know.
    assert request_values <= {status.value for status in BookingRequestStatus}
    assert notification_values <= {kind.value for kind in NotificationKind}


def test_the_revision_follows_0031_and_fits_alembics_version_column(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)

    assert migration.down_revision == "0031_add_withdrawn_registrations"
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(migration.revision) <= 32


def test_upgrade_adds_the_columns_the_enum_values_then_widens_the_pending_index(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "ALTER TABLE bookings ADD COLUMN hold_expires_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE venue_booking_requests ADD COLUMN booking_id INTEGER",
        "COMMIT",
        "ALTER TYPE booking_request_status ADD VALUE IF NOT EXISTS 'on_hold'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'venue_hold_placed'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'venue_hold_expiry_changed'",
        "BEGIN",
        # SCRUM-42 AC7: a request On Hold blocks a second one, like a Pending one.
        "DROP INDEX uq_venue_booking_requests_pending",
        "CREATE UNIQUE INDEX uq_venue_booking_requests_pending ON venue_booking_requests "
        "(event_id, venue_id, starts_at, ends_at) "
        "WHERE status IN ('pending', 'conflicting', 'on_hold')",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_deletes_the_holds_drops_the_columns_and_rebuilds_both_types(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    """Requests On Hold go before the bookings they point at.

    The pending index is dropped around the request rebuild, as in 0028, and comes
    back as 0028 left it.
    """
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM venue_booking_requests WHERE status = 'on_hold'",
        "DELETE FROM bookings WHERE status = 'tentative' AND hold_expires_at IS NOT NULL",
        "ALTER TABLE venue_booking_requests DROP COLUMN booking_id",
        "ALTER TABLE bookings DROP COLUMN hold_expires_at",
        "DROP INDEX uq_venue_booking_requests_pending",
        "ALTER TYPE booking_request_status RENAME TO booking_request_status_old",
        "CREATE TYPE booking_request_status AS ENUM ('pending', 'withdrawn', 'approved', "
        "'rejected', 'conflicting')",
        "ALTER TABLE venue_booking_requests ALTER COLUMN status "
        "TYPE booking_request_status USING status::text::booking_request_status",
        "DROP TYPE booking_request_status_old",
        # Back to main's index (0028), Conflicting included, not a narrower one.
        "CREATE UNIQUE INDEX uq_venue_booking_requests_pending ON venue_booking_requests "
        "(event_id, venue_id, starts_at, ends_at) WHERE status IN ('pending', 'conflicting')",
        "DELETE FROM notifications WHERE kind = 'venue_hold_placed'",
        "DELETE FROM notifications WHERE kind = 'venue_hold_expiry_changed'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
