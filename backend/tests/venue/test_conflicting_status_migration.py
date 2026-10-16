"""Unit tests for migration 0028, SCRUM-44's Conflicting status.

It adds ``conflicting`` to ``booking_request_status`` and to ``booking_status``.
``flask db check`` doesn't compare enum members, so these tests check the migration's
value lists against the models and render its SQL for Postgres offline, so the upgrade
and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.venue.models import BookingRequestStatus, BookingStatus

pytestmark = pytest.mark.scrum_44

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0028_add_conflicting_status.py"
#: The migration that left ``booking_request_status`` as it was before this one.
REQUEST_STATUS_MIGRATION_BELOW = "0025_add_booking_request_decisions.py"


def test_the_previous_request_statuses_are_what_exists_after_the_migrations_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(REQUEST_STATUS_MIGRATION_BELOW)
    after_below = set(below.PREVIOUS_REQUEST_STATUS_VALUES) | set(below.ADDED_REQUEST_STATUS_VALUES)

    assert set(migration.PREVIOUS_REQUEST_STATUS_VALUES) == after_below


def test_the_migrations_value_lists_are_the_models_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    request_values = (*migration.PREVIOUS_REQUEST_STATUS_VALUES, "conflicting")
    booking_values = (*migration.PREVIOUS_BOOKING_STATUS_VALUES, "conflicting")
    assert set(request_values) == {status.value for status in BookingRequestStatus}
    assert set(booking_values) == {status.value for status in BookingStatus}


def test_the_revision_id_fits_alembics_version_column(load_migration: LoadMigration) -> None:
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(load_migration(MIGRATION).revision) <= 32


def test_upgrade_adds_the_value_to_both_types_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "COMMIT",
        "ALTER TYPE booking_request_status ADD VALUE IF NOT EXISTS 'conflicting'",
        "ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'conflicting'",
        "BEGIN",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_puts_conflicting_rows_back_and_rebuilds_both_types(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    """The pending index is dropped around the request rebuild, as in 0025."""
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DROP INDEX uq_venue_booking_requests_pending",
        "UPDATE venue_booking_requests SET status='pending' WHERE status = 'conflicting'",
        "ALTER TYPE booking_request_status RENAME TO booking_request_status_old",
        "CREATE TYPE booking_request_status AS ENUM ('pending', 'withdrawn', 'approved', "
        "'rejected')",
        "ALTER TABLE venue_booking_requests ALTER COLUMN status "
        "TYPE booking_request_status USING status::text::booking_request_status",
        "DROP TYPE booking_request_status_old",
        "CREATE UNIQUE INDEX uq_venue_booking_requests_pending",
        "UPDATE bookings SET status='confirmed' WHERE status = 'conflicting'",
        "ALTER TYPE booking_status RENAME TO booking_status_old",
        "CREATE TYPE booking_status AS ENUM ('tentative', 'confirmed', 'cancelled')",
        "ALTER TABLE bookings ALTER COLUMN status "
        "TYPE booking_status USING status::text::booking_status",
        "DROP TYPE booking_status_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
