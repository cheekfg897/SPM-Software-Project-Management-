"""Unit tests for migration 0018, which adds SCRUM-32's schema (ADR-0029).

It adds the ``awaiting_clarification`` status, and a ``clarification_requested`` and a
``clarification_answered`` kind to both the event history and the notifications.
``flask db check`` doesn't compare enum members, so these tests check the migration's
value lists against the models and against migration 0017, which it builds on, and
render its SQL for Postgres offline so the upgrade and the downgrade are tested
without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind, EventRequestStatus
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_32

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
AssertMigrationAndModelAgree = Callable[[tuple[str, ...], tuple[str, ...], set[str]], None]

MIGRATION = "0018_add_clarification_status_and_kinds.py"
APPROVAL_MIGRATION = "0017_add_approved_status_and_decision_kinds.py"
DRAFTS_MIGRATION = "0014_allow_incomplete_draft_requests.py"


# --------------------------------------------------------------------------
# The previous lists are what migration 0017 left behind
# --------------------------------------------------------------------------


def test_the_previous_statuses_are_what_exists_after_migration_0017_in_postgres_order(
    load_migration: LoadMigration,
) -> None:
    previous = load_migration(MIGRATION).PREVIOUS_STATUS_VALUES
    approval = load_migration(APPROVAL_MIGRATION)
    after_0017 = approval.PREVIOUS_STATUS_VALUES + approval.ADDED_STATUS_VALUES

    # A tuple, not a set: downgrade rebuilds the type in this order.
    assert previous == after_0017


def test_the_previous_history_kinds_are_what_exists_after_migration_0017(
    load_migration: LoadMigration,
) -> None:
    previous = load_migration(MIGRATION).PREVIOUS_HISTORY_KIND_VALUES
    approval = load_migration(APPROVAL_MIGRATION)
    after_0017 = set(approval.PREVIOUS_HISTORY_KIND_VALUES) | set(
        approval.ADDED_HISTORY_KIND_VALUES
    )

    assert set(previous) == after_0017


def test_the_previous_notification_kinds_are_what_exists_after_migration_0017(
    load_migration: LoadMigration,
) -> None:
    previous = load_migration(MIGRATION).PREVIOUS_NOTIFICATION_KIND_VALUES
    approval = load_migration(APPROVAL_MIGRATION)
    after_0017 = set(approval.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(
        approval.ADDED_NOTIFICATION_KIND_VALUES
    )

    assert set(previous) == after_0017


# --------------------------------------------------------------------------
# The migration adds exactly what the models gained
# --------------------------------------------------------------------------


def test_migration_and_model_agree_on_the_status_values(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_STATUS_VALUES,
        migration.ADDED_STATUS_VALUES,
        {status.value for status in EventRequestStatus},
    )


def test_migration_and_model_agree_on_the_history_kinds(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_HISTORY_KIND_VALUES,
        migration.ADDED_HISTORY_KIND_VALUES,
        {kind.value for kind in EventHistoryKind},
    )


def test_migration_and_model_agree_on_the_notification_kinds(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        migration.ADDED_NOTIFICATION_KIND_VALUES,
        {kind.value for kind in NotificationKind},
    )


# --------------------------------------------------------------------------
# The SQL it runs on Postgres
# --------------------------------------------------------------------------


def test_upgrade_adds_every_value_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "ALTER TYPE event_request_status ADD VALUE IF NOT EXISTS 'awaiting_clarification'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'clarification_requested'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'clarification_answered'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'clarification_requested'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'clarification_answered'",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)
    # Postgres won't let a transaction use an enum value it added, so every addition
    # sits between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index("ADD VALUE")
    assert sql.rindex("ADD VALUE") < sql.index("BEGIN")
    assert "ADD COLUMN" not in sql


def test_downgrade_rebuilds_the_three_types_and_returns_waiting_requests_to_under_review(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    # The check 0014 added, that a request past the draft stage has its details,
    # compares the status, so it would stop the column changing type.
    drafts = load_migration(DRAFTS_MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'clarification_requested'",
        "DELETE FROM notifications WHERE kind = 'clarification_answered'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted', "
        "'coordinator_assigned', 'equipment_requested', 'significant_change', "
        "'event_request_approved', 'event_request_rejected')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "DELETE FROM event_history_entries WHERE kind = 'clarification_requested'",
        "DELETE FROM event_history_entries WHERE kind = 'clarification_answered'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "CREATE TYPE event_history_entry_kind AS ENUM ('coordinator_assigned', "
        "'coordinator_reassigned', 'field_changed', 'event_completed', 'review_started', "
        "'decision_recorded')",
        "ALTER TABLE event_history_entries ALTER COLUMN kind "
        "TYPE event_history_entry_kind USING kind::text::event_history_entry_kind",
        "DROP TYPE event_history_entry_kind_old",
        "UPDATE event_requests SET status = 'under_review' WHERE status = 'awaiting_clarification'",
        "ALTER TYPE event_request_status RENAME TO event_request_status_old",
        "CREATE TYPE event_request_status AS ENUM ('submitted', 'draft', 'under_review', "
        "'confirmed', 'completed', 'cancelled', 'rejected', 'approved')",
        f"ALTER TABLE event_requests DROP CONSTRAINT {drafts.CHECK_NAME}",
        "ALTER TABLE event_requests ALTER COLUMN status "
        "TYPE event_request_status USING status::text::event_request_status",
        f"ALTER TABLE event_requests ADD CONSTRAINT {drafts.CHECK_NAME} "
        f"CHECK ({drafts.CHECK_CONDITION})",
        "DROP TYPE event_request_status_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "DROP COLUMN" not in sql
