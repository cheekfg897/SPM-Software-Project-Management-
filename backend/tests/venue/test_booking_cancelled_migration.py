"""Unit tests for migration 0051, SCRUM-111's cancelled booking (ADR-0117).

``booking_request_status`` gains ``cancelled``, the arrangement whose approved booking
the coordinator cancelled (AC1). ``notification_kind`` gains
``venue_booking_cancelled``, Venue Staff's notice (AC3), and
``safety_review_venue_cancelled``, the Safety Officers' (AC2).
``event_history_entry_kind`` gains ``venue_booking_cancelled``, the entry that records
the cancellation and its reason (AC5). ``flask db check`` doesn't compare enum members,
so these tests check the migration's value lists against the models and the migrations
below it, and render its SQL for Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind
from app.modules.venue.models import BookingRequestStatus

pytestmark = pytest.mark.scrum_111

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0051_add_booking_cancelled.py"
#: The last migrations to change each type before this one.
REQUEST_STATUS_BELOW = "0039_flag_alternative_venues.py"
KINDS_BELOW = "0049_add_venue_booking_reconfirmed.py"


def _model_values(enum_type: type) -> set[str]:
    return {member.value for member in enum_type}


def test_it_follows_the_needs_reassessment_migration(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.down_revision == "0050_add_needs_reassessment"
    assert migration.revision == "0051_add_booking_cancelled"
    # ``alembic_version`` holds at most 32 characters.
    assert len(migration.revision) <= 32


def test_the_previous_values_are_what_the_migrations_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    status_below = load_migration(REQUEST_STATUS_BELOW)
    kinds_below = load_migration(KINDS_BELOW)

    # In Postgres's order: each ADD VALUE appends.
    statuses_left = (
        *status_below.PREVIOUS_REQUEST_STATUS_VALUES,
        *status_below.ADDED_REQUEST_STATUS_VALUES,
    )
    notifications_left = (
        *kinds_below.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *kinds_below.ADDED_NOTIFICATION_KIND_VALUES,
    )
    history_left = (
        *kinds_below.PREVIOUS_HISTORY_KIND_VALUES,
        *kinds_below.ADDED_HISTORY_KIND_VALUES,
    )

    assert statuses_left == migration.PREVIOUS_REQUEST_STATUS_VALUES
    assert notifications_left == migration.PREVIOUS_NOTIFICATION_KIND_VALUES
    assert history_left == migration.PREVIOUS_HISTORY_KIND_VALUES


def test_it_adds_the_new_status_and_kinds(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.ADDED_REQUEST_STATUS_VALUES == ("cancelled",)
    assert migration.ADDED_NOTIFICATION_KIND_VALUES == (
        "venue_booking_cancelled",
        "safety_review_venue_cancelled",
    )
    assert migration.ADDED_HISTORY_KIND_VALUES == ("venue_booking_cancelled",)


def test_with_the_values_added_each_type_holds_exactly_the_models_values(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    statuses = {*migration.PREVIOUS_REQUEST_STATUS_VALUES, *migration.ADDED_REQUEST_STATUS_VALUES}
    notification_kinds = {
        *migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *migration.ADDED_NOTIFICATION_KIND_VALUES,
    }
    history_kinds = {*migration.PREVIOUS_HISTORY_KIND_VALUES, *migration.ADDED_HISTORY_KIND_VALUES}

    assert statuses == _model_values(BookingRequestStatus)
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
        "ALTER TYPE booking_request_status ADD VALUE IF NOT EXISTS 'cancelled'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'venue_booking_cancelled'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'safety_review_venue_cancelled'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'venue_booking_cancelled'",
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
        "DELETE FROM notifications WHERE kind = 'venue_booking_cancelled'",
        "DELETE FROM notifications WHERE kind = 'safety_review_venue_cancelled'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'replacement_venue_approved', 'venue_booking_reconfirmed')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "DELETE FROM event_history_entries WHERE kind = 'venue_booking_cancelled'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "CREATE TYPE event_history_entry_kind AS ENUM ('coordinator_assigned'",
        "'safety_approval_withdrawn', 'venue_booking_reconfirmed')",
        "DROP TYPE event_history_entry_kind_old",
        # A cancelled arrangement no longer holds its venue, as a released one doesn't,
        # so it keeps its meaning; the pending index can't be re-created against the
        # renamed type, so it is dropped and put back.
        "DROP INDEX uq_venue_booking_requests_pending",
        "UPDATE venue_booking_requests SET status = 'released' WHERE status = 'cancelled'",
        "ALTER TYPE booking_request_status RENAME TO booking_request_status_old",
        "CREATE TYPE booking_request_status AS ENUM ('pending', 'withdrawn', 'approved', "
        "'rejected', 'conflicting', 'on_hold', 'expired', 'released')",
        "ALTER TABLE venue_booking_requests ALTER COLUMN status "
        "TYPE booking_request_status USING status::text::booking_request_status",
        "DROP TYPE booking_request_status_old",
        "CREATE UNIQUE INDEX uq_venue_booking_requests_pending ON venue_booking_requests "
        "(event_id, venue_id, starts_at, ends_at) "
        "WHERE status IN ('pending', 'conflicting', 'on_hold')",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "'cancelled')" not in sql
