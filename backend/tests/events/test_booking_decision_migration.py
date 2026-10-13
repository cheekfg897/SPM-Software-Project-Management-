"""Unit tests for migration 0025, SCRUM-43's venue booking decisions.

It adds ``decision_reason`` to ``venue_booking_requests``, ``approved`` and
``rejected`` to ``booking_request_status``, and ``venue_booking_approved`` and
``venue_booking_rejected`` to ``event_history_entry_kind`` and ``notification_kind``.
``flask db check`` doesn't compare enum members, so these tests check the migration's
value lists against the models and the migrations below it, and render its SQL for
Postgres offline so the upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind
from app.modules.venue.models import BookingRequestStatus

pytestmark = pytest.mark.scrum_43

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
AssertMigrationAndModelAgree = Callable[[tuple[str, ...], tuple[str, ...], set[str]], None]

MIGRATION = "0025_add_booking_request_decisions.py"
#: The last migration to change the request status, and the last to change both kinds.
STATUS_MIGRATION_BELOW = "0023_add_withdrawn_arrangements.py"
KIND_MIGRATION_BELOW = "0024_add_equipment_review_outcome.py"


def test_the_previous_values_are_what_exists_after_the_migrations_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    status_below = load_migration(STATUS_MIGRATION_BELOW)
    kinds_below = load_migration(KIND_MIGRATION_BELOW)
    statuses_after_below = set(status_below.PREVIOUS_REQUEST_STATUS_VALUES) | set(
        status_below.ADDED_REQUEST_STATUS_VALUES
    )
    history_after_below = set(kinds_below.PREVIOUS_HISTORY_KIND_VALUES) | set(
        kinds_below.ADDED_HISTORY_KIND_VALUES
    )
    notifications_after_below = set(kinds_below.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(
        kinds_below.ADDED_NOTIFICATION_KIND_VALUES
    )

    assert set(migration.PREVIOUS_REQUEST_STATUS_VALUES) == statuses_after_below
    assert set(migration.PREVIOUS_HISTORY_KIND_VALUES) == history_after_below
    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) == notifications_after_below


def test_migration_and_models_agree_on_the_new_values(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    """``on_hold`` is SCRUM-75's, so the model must not have it yet either."""
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_REQUEST_STATUS_VALUES,
        migration.ADDED_REQUEST_STATUS_VALUES,
        {status.value for status in BookingRequestStatus},
    )
    assert_migration_and_model_agree(
        migration.PREVIOUS_HISTORY_KIND_VALUES,
        migration.ADDED_HISTORY_KIND_VALUES,
        {kind.value for kind in EventHistoryKind},
    )
    assert_migration_and_model_agree(
        migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        migration.ADDED_NOTIFICATION_KIND_VALUES,
        {kind.value for kind in NotificationKind},
    )


def test_the_revision_id_fits_alembics_version_column(load_migration: LoadMigration) -> None:
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(load_migration(MIGRATION).revision) <= 32


def test_upgrade_adds_the_column_then_the_values_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "ALTER TABLE venue_booking_requests ADD COLUMN decision_reason TEXT",
        "COMMIT",
        "ALTER TYPE booking_request_status ADD VALUE IF NOT EXISTS 'approved'",
        "ALTER TYPE booking_request_status ADD VALUE IF NOT EXISTS 'rejected'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'venue_booking_approved'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'venue_booking_rejected'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'venue_booking_approved'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'venue_booking_rejected'",
        "BEGIN",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_deletes_the_decided_requests_and_rebuilds_the_types(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    """The pending index is dropped around the status rebuild, as in 0023."""
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM venue_booking_requests WHERE status IN ('approved', 'rejected')",
        "DROP COLUMN decision_reason",
        "DROP INDEX uq_venue_booking_requests_pending",
        "ALTER TYPE booking_request_status RENAME TO booking_request_status_old",
        "CREATE TYPE booking_request_status AS ENUM ('pending', 'withdrawn')",
        "ALTER TABLE venue_booking_requests ALTER COLUMN status "
        "TYPE booking_request_status USING status::text::booking_request_status",
        "DROP TYPE booking_request_status_old",
        "CREATE UNIQUE INDEX uq_venue_booking_requests_pending",
        "DELETE FROM event_history_entries WHERE kind = 'venue_booking_approved'",
        "DELETE FROM event_history_entries WHERE kind = 'venue_booking_rejected'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "DROP TYPE event_history_entry_kind_old",
        "DELETE FROM notifications WHERE kind = 'venue_booking_approved'",
        "DELETE FROM notifications WHERE kind = 'venue_booking_rejected'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
