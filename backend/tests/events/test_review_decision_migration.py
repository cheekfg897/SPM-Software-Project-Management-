"""Unit tests for migration 0017, which adds SCRUM-31's schema (ADR-0028).

It adds ``notifications.detail``, the ``approved`` status, the ``review_started`` and
``decision_recorded`` event history kinds, and the ``event_request_approved`` and
``event_request_rejected`` notification kinds. ``flask db check`` doesn't compare enum
members, so these tests check the migration's value lists against the models and the
earlier migrations they build on, and render its SQL for Postgres offline so the
upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind, EventRequestStatus
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_31

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0017_add_approved_status_and_decision_kinds.py"
EVENT_REQUESTS_MIGRATION = "0002_create_event_requests_table.py"
STATUSES_MIGRATION = "0006_add_event_request_statuses.py"
NOTIFICATIONS_MIGRATION = "0009_create_notifications_table.py"
ASSIGNMENT_MIGRATION = "0010_add_coordinator_assignment_and_event_history.py"
EQUIPMENT_MIGRATION = "0011_create_event_equipment_lines_table.py"
REASSIGNMENT_MIGRATION = "0012_add_reassignment_history_kind.py"
NOTES_MIGRATION = "0015_add_event_notes_and_change_kinds.py"
COMPLETION_MIGRATION = "0016_add_event_completed_history_kind.py"


def _assert_migration_and_model_agree(
    previous_values: tuple[str, ...], added_values: tuple[str, ...], model_values: set[str]
) -> None:
    previous = set(previous_values)
    added = set(added_values)

    # Subset, not equality: a later migration could add a further value this one
    # doesn't know about, as 0015 later did to 0010 and 0012's history kinds.
    assert previous | added <= model_values
    assert previous.isdisjoint(added)


# --------------------------------------------------------------------------
# The previous lists are what the earlier migrations left behind
# --------------------------------------------------------------------------


def test_the_previous_statuses_are_what_exists_after_migration_0006_in_postgres_order(
    load_migration: LoadMigration,
) -> None:
    previous = load_migration(MIGRATION).PREVIOUS_STATUS_VALUES
    after_0006 = (
        load_migration(EVENT_REQUESTS_MIGRATION).STATUS_VALUES
        + load_migration(STATUSES_MIGRATION).ADDED_STATUS_VALUES
    )

    # A tuple, not a set: downgrade rebuilds the type in this order.
    assert previous == after_0006


def test_the_previous_history_kinds_are_what_exists_after_migration_0016(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    after_0016 = (
        set(load_migration(ASSIGNMENT_MIGRATION).HISTORY_KIND_VALUES)
        | set(load_migration(REASSIGNMENT_MIGRATION).ADDED_HISTORY_KIND_VALUES)
        | set(load_migration(NOTES_MIGRATION).ADDED_HISTORY_KIND_VALUES)
        | set(load_migration(COMPLETION_MIGRATION).ADDED_HISTORY_KIND_VALUES)
    )

    assert set(migration.PREVIOUS_HISTORY_KIND_VALUES) == after_0016


def test_the_previous_notification_kinds_are_what_exists_after_migration_0015(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    after_0015 = (
        set(load_migration(NOTIFICATIONS_MIGRATION).KIND_VALUES)
        | set(load_migration(ASSIGNMENT_MIGRATION).ADDED_NOTIFICATION_KIND_VALUES)
        | set(load_migration(EQUIPMENT_MIGRATION).ADDED_KIND_VALUES)
        | set(load_migration(NOTES_MIGRATION).ADDED_NOTIFICATION_KIND_VALUES)
    )

    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) == after_0015


# --------------------------------------------------------------------------
# The migration adds exactly what the models gained
# --------------------------------------------------------------------------


def test_migration_and_model_agree_on_the_status_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    _assert_migration_and_model_agree(
        migration.PREVIOUS_STATUS_VALUES,
        migration.ADDED_STATUS_VALUES,
        {status.value for status in EventRequestStatus},
    )


def test_migration_and_model_agree_on_the_history_kinds(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    _assert_migration_and_model_agree(
        migration.PREVIOUS_HISTORY_KIND_VALUES,
        migration.ADDED_HISTORY_KIND_VALUES,
        {kind.value for kind in EventHistoryKind},
    )


def test_migration_and_model_agree_on_the_notification_kinds(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    _assert_migration_and_model_agree(
        migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        migration.ADDED_NOTIFICATION_KIND_VALUES,
        {kind.value for kind in NotificationKind},
    )


# --------------------------------------------------------------------------
# The SQL it runs on Postgres
# --------------------------------------------------------------------------


def test_upgrade_adds_the_detail_column_then_every_value_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert "ALTER TABLE notifications ADD COLUMN detail TEXT" in sql
    assert "ALTER TYPE event_request_status ADD VALUE IF NOT EXISTS 'approved'" in sql
    assert "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'review_started'" in sql
    assert "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'decision_recorded'" in sql
    assert "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'event_request_approved'" in sql
    assert "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'event_request_rejected'" in sql
    # Postgres won't let a transaction use an enum value it added, so every addition
    # sits between a COMMIT and a new BEGIN, after the column is added.
    assert sql.index("ADD COLUMN") < sql.index("COMMIT") < sql.index("ADD VALUE")
    assert sql.rindex("ADD VALUE") < sql.index("BEGIN")


def test_downgrade_rebuilds_the_three_types_then_drops_the_column(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'event_request_approved'",
        "DELETE FROM notifications WHERE kind = 'event_request_rejected'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted', "
        "'coordinator_assigned', 'equipment_requested', 'significant_change')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "DELETE FROM event_history_entries WHERE kind = 'review_started'",
        "DELETE FROM event_history_entries WHERE kind = 'decision_recorded'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "CREATE TYPE event_history_entry_kind AS ENUM "
        "('coordinator_assigned', 'coordinator_reassigned', 'field_changed', 'event_completed')",
        "ALTER TABLE event_history_entries ALTER COLUMN kind "
        "TYPE event_history_entry_kind USING kind::text::event_history_entry_kind",
        "DROP TYPE event_history_entry_kind_old",
        "UPDATE event_requests SET status = 'under_review' WHERE status = 'approved'",
        # 0014's check compares status, which blocks re-typing the column on Postgres.
        "ALTER TABLE event_requests DROP CONSTRAINT ck_event_requests_details_unless_draft",
        "ALTER TYPE event_request_status RENAME TO event_request_status_old",
        "CREATE TYPE event_request_status AS ENUM ('submitted', 'draft', 'under_review', "
        "'confirmed', 'completed', 'cancelled', 'rejected')",
        "ALTER TABLE event_requests ALTER COLUMN status "
        "TYPE event_request_status USING status::text::event_request_status",
        "ALTER TABLE event_requests ADD CONSTRAINT ck_event_requests_details_unless_draft "
        "CHECK (status = 'draft' OR (proposed_date IS NOT NULL AND end_date IS NOT NULL AND "
        "start_time IS NOT NULL AND end_time IS NOT NULL AND expected_attendance IS NOT NULL))",
        "DROP TYPE event_request_status_old",
        "ALTER TABLE notifications DROP COLUMN detail",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
