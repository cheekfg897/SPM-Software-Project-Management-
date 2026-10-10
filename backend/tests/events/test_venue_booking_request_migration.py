"""Unit tests for migration 0020, which adds SCRUM-42's venue booking requests.

The migration creates ``venue_booking_requests`` with its ``booking_request_status``
enum, and adds ``venue_booking_requested`` to ``event_history_entry_kind`` (the audit
entry written when a request is raised) and to ``notification_kind`` (Venue Staff's
notice). ``flask db check`` doesn't compare enum members, so these tests check the
value lists against the models and the migrations below, and render the SQL for
Postgres offline so the upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind
from app.modules.venue.models import BookingRequestStatus

pytestmark = pytest.mark.scrum_42

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0020_add_venue_booking_requests.py"
#: The last migrations to change each enum before this one.
HISTORY_MIGRATION_BELOW = "0018_add_clarification_status_and_kinds.py"
NOTIFICATION_MIGRATION_BELOW = "0019_add_review_notification_kinds.py"


def test_the_previous_history_kinds_are_what_exists_after_the_migration_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(HISTORY_MIGRATION_BELOW)
    after_below = set(below.PREVIOUS_HISTORY_KIND_VALUES) | set(below.ADDED_HISTORY_KIND_VALUES)

    assert set(migration.PREVIOUS_HISTORY_KIND_VALUES) == after_below


def test_the_previous_notification_kinds_are_what_exists_after_the_migration_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(NOTIFICATION_MIGRATION_BELOW)
    after_below = set(below.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(
        below.ADDED_NOTIFICATION_KIND_VALUES
    )

    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) == after_below


def test_migration_and_models_agree_on_the_enum_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    # Subset, not equality, for the shared enums: a later migration could add a
    # further kind this one doesn't know about.
    history = set(migration.PREVIOUS_HISTORY_KIND_VALUES) | set(migration.ADDED_HISTORY_KIND_VALUES)
    notifications = set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(
        migration.ADDED_NOTIFICATION_KIND_VALUES
    )
    assert history <= {kind.value for kind in EventHistoryKind}
    assert notifications <= {kind.value for kind in NotificationKind}
    assert migration.ADDED_HISTORY_KIND_VALUES == ("venue_booking_requested",)
    assert migration.ADDED_NOTIFICATION_KIND_VALUES == ("venue_booking_requested",)
    assert set(migration.REQUEST_STATUS_VALUES) == {s.value for s in BookingRequestStatus}


def test_upgrade_creates_the_table_and_adds_both_kinds_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    history = (
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'venue_booking_requested'"
    )
    notification = "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'venue_booking_requested'"
    assert "CREATE TYPE booking_request_status AS ENUM ('pending')" in sql
    assert "CREATE TABLE venue_booking_requests" in sql
    # Postgres won't let a transaction use an enum value it added, so the additions sit
    # after the table, between a COMMIT and a new BEGIN.
    assert sql.index("CREATE TABLE venue_booking_requests") < sql.index("COMMIT")
    assert sql.index("COMMIT") < sql.index(history) < sql.index("BEGIN", sql.index("COMMIT"))
    assert sql.index("COMMIT") < sql.index(notification) < sql.index("BEGIN", sql.index("COMMIT"))


def test_downgrade_drops_the_table_and_its_type_and_rebuilds_both_kind_types(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'venue_booking_requested'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted', "
        "'coordinator_assigned', 'equipment_requested', 'significant_change', "
        "'event_request_approved', 'event_request_rejected', 'clarification_requested', "
        "'clarification_answered', 'request_assigned')",
        "DROP TYPE notification_kind_old",
        "DELETE FROM event_history_entries WHERE kind = 'venue_booking_requested'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "CREATE TYPE event_history_entry_kind AS ENUM ('coordinator_assigned', "
        "'coordinator_reassigned', 'field_changed', 'event_completed', 'review_started', "
        "'decision_recorded', 'clarification_requested', 'clarification_answered')",
        "DROP TYPE event_history_entry_kind_old",
        "DROP TABLE venue_booking_requests",
        "DROP TYPE booking_request_status",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
