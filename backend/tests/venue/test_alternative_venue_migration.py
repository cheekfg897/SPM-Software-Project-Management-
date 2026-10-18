"""Unit tests for migration 0039, SCRUM-92's alternative venue flags (ADR-0053).

It adds the ``unavailability_category`` type, ``venue_blocks.category``, the
``alternative_venue_flags`` table, ``venue_booking_requests.replaces_request_id``, the
``released`` request status and three history and notification kinds. ``flask db
check`` doesn't compare enum members, so these tests check the migration's value lists
against the models and the migrations below it, and render its SQL for Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind
from app.modules.venue.models import BookingRequestStatus, UnavailabilityCategory

pytestmark = pytest.mark.scrum_92

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0039_flag_alternative_venues.py"
#: The migration below, the last to change the request statuses and the history and
#: notification kinds.
MIGRATION_BELOW = "0037_expire_tentative_holds.py"


def _model_values(enum_type: type) -> set[str]:
    return {member.value for member in enum_type}


def test_it_follows_the_expire_holds_migration(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.down_revision == "0037_expire_tentative_holds"
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(migration.revision) <= 32


def test_the_previous_values_are_what_the_migrations_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(MIGRATION_BELOW)

    # In Postgres's order: each ADD VALUE appends.
    history_left = (
        *below.PREVIOUS_HISTORY_KIND_VALUES,
        *below.ADDED_HISTORY_KIND_VALUES,
    )
    notifications_left = (
        *below.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *below.ADDED_NOTIFICATION_KIND_VALUES,
    )
    statuses_left = (
        *below.PREVIOUS_REQUEST_STATUS_VALUES,
        *below.ADDED_REQUEST_STATUS_VALUES,
    )

    assert history_left == migration.PREVIOUS_HISTORY_KIND_VALUES
    assert notifications_left == migration.PREVIOUS_NOTIFICATION_KIND_VALUES
    assert statuses_left == migration.PREVIOUS_REQUEST_STATUS_VALUES


def test_the_migrations_values_are_the_models_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert set(migration.CATEGORY_VALUES) == _model_values(UnavailabilityCategory)
    assert {
        *migration.PREVIOUS_REQUEST_STATUS_VALUES,
        *migration.ADDED_REQUEST_STATUS_VALUES,
    } == _model_values(BookingRequestStatus)
    assert {
        *migration.PREVIOUS_HISTORY_KIND_VALUES,
        *migration.ADDED_HISTORY_KIND_VALUES,
    } == _model_values(EventHistoryKind)
    # Subset, not equality: a later migration (0041 SCRUM-50) adds a further kind.
    assert {
        *migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *migration.ADDED_NOTIFICATION_KIND_VALUES,
    } <= _model_values(NotificationKind)


def test_upgrade_adds_the_columns_and_table_then_the_values_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "CREATE TYPE unavailability_category AS ENUM ('maintenance', 'equipment_failure', "
        "'renovation', 'safety_concern', 'other')",
        "ALTER TABLE venue_blocks ADD COLUMN category unavailability_category "
        "DEFAULT 'other' NOT NULL",
        "ALTER TABLE venue_blocks ALTER COLUMN category DROP DEFAULT",
        "CREATE TABLE alternative_venue_flags",
        "FOREIGN KEY(booking_request_id) REFERENCES venue_booking_requests (id) ON DELETE CASCADE",
        "FOREIGN KEY(venue_block_id) REFERENCES venue_blocks (id) ON DELETE CASCADE",
        "ALTER TABLE venue_booking_requests ADD COLUMN replaces_request_id INTEGER",
        "ALTER TABLE venue_booking_requests ADD CONSTRAINT "
        "fk_venue_booking_requests_replaces_request_id FOREIGN KEY(replaces_request_id) "
        "REFERENCES venue_booking_requests (id)",
        "COMMIT",
        "ALTER TYPE booking_request_status ADD VALUE IF NOT EXISTS 'released'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'alternative_venue_needed'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'safety_approval_withdrawn'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'alternative_venue_needed'",
        "BEGIN",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)
    # Created once, before both columns that use it.
    assert sql.count("CREATE TYPE unavailability_category") == 1


def test_downgrade_removes_everything_and_rebuilds_each_type_with_mains_values(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'alternative_venue_needed'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'venue_hold_expiring', 'venue_hold_expired')",
        "DROP TYPE notification_kind_old",
        "DELETE FROM event_history_entries WHERE kind = 'alternative_venue_needed'",
        "DELETE FROM event_history_entries WHERE kind = 'safety_approval_withdrawn'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "'equipment_preparation_updated', 'venue_hold_expired')",
        "DROP TYPE event_history_entry_kind_old",
        "DROP INDEX uq_venue_booking_requests_pending",
        "UPDATE venue_booking_requests SET status='withdrawn' WHERE status = 'released'",
        "CREATE TYPE booking_request_status AS ENUM ('pending', 'withdrawn', 'approved', "
        "'rejected', 'conflicting', 'on_hold', 'expired')",
        "ALTER TABLE venue_booking_requests ALTER COLUMN status "
        "TYPE booking_request_status USING status::text::booking_request_status",
        "DROP TYPE booking_request_status_old",
        "CREATE UNIQUE INDEX uq_venue_booking_requests_pending ON venue_booking_requests "
        "(event_id, venue_id, starts_at, ends_at) "
        "WHERE status IN ('pending', 'conflicting', 'on_hold')",
        "ALTER TABLE venue_booking_requests DROP CONSTRAINT "
        "fk_venue_booking_requests_replaces_request_id",
        "ALTER TABLE venue_booking_requests DROP COLUMN replaces_request_id",
        "DROP TABLE alternative_venue_flags",
        "ALTER TABLE venue_blocks DROP COLUMN category",
        "DROP TYPE unavailability_category",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
