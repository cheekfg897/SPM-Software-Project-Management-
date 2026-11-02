"""Unit tests for migration 0055, SCRUM-57's change request decisions (ADR-0127).

The migration gives ``event_change_requests`` who decided a request, when, and why
(AC4, AC6), with checks that a decided request has a time and a decider and that a
rejected one has a reason (AC3). It adds ``change_request_approved``,
``change_request_rejected`` and ``event_rescheduled`` to ``notification_kind`` (AC4,
AC7). ``flask db check`` doesn't compare enum members, so these tests check the value
lists against the models and the migration below, and render the SQL for Postgres
offline so the upgrade and the downgrade are tested without a database. The model's
copies of the checks are tested against the unit suite's database.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events.models import ChangeRequestStatus, EventChangeRequest, EventRequest
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_57

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0055_add_change_request_decisions.py"
#: SCRUM-56's migration, the one this stacks on and the last to change the kinds.
MIGRATION_BELOW = "0053_create_event_change_requests_table.py"
ADDED = ("change_request_approved", "change_request_rejected", "event_rescheduled")


def test_the_previous_notification_kinds_are_what_the_migration_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(MIGRATION_BELOW)
    # In Postgres's order: each ADD VALUE appends.
    left_below = (
        *below.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *below.ADDED_NOTIFICATION_KIND_VALUES,
    )

    assert left_below == migration.PREVIOUS_NOTIFICATION_KIND_VALUES
    assert migration.PREVIOUS_NOTIFICATION_KIND_VALUES[-2:] == (
        "change_request_raised",
        "change_request_withdrawn",
    )


def test_it_adds_the_models_new_kinds_and_follows_scrum_56(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.ADDED_NOTIFICATION_KIND_VALUES == ADDED
    assert set(ADDED).isdisjoint(migration.PREVIOUS_NOTIFICATION_KIND_VALUES)
    assert migration.down_revision == "0053_create_change_requests"
    # ``alembic_version`` holds at most 32 characters.
    assert migration.revision == "0055_decide_change_requests"
    assert len(migration.revision) <= 32


def test_with_the_kinds_added_the_type_holds_exactly_the_models_kinds(
    load_migration: LoadMigration,
) -> None:
    """The newest migration to change ``notification_kind`` leaves no kind out."""
    migration = load_migration(MIGRATION)
    notification_kinds = {
        *migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *migration.ADDED_NOTIFICATION_KIND_VALUES,
    }

    assert notification_kinds == {kind.value for kind in NotificationKind}


def test_upgrade_adds_the_decision_columns_and_checks_then_the_kinds(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert "ALTER TABLE event_change_requests ADD COLUMN decided_at TIMESTAMP WITH TIME ZONE" in sql
    assert "ALTER TABLE event_change_requests ADD COLUMN decided_by INTEGER" in sql
    assert "ALTER TABLE event_change_requests ADD COLUMN decision_reason TEXT" in sql
    assert (
        "ALTER TABLE event_change_requests ADD CONSTRAINT fk_event_change_requests_decided_by "
        "FOREIGN KEY(decided_by) REFERENCES users (id)"
    ) in sql
    assert (
        "ALTER TABLE event_change_requests ADD CONSTRAINT "
        "ck_event_change_requests_decided_has_time CHECK (status NOT IN ('approved', "
        "'rejected') OR (decided_at IS NOT NULL AND decided_by IS NOT NULL))"
    ) in sql
    assert (
        "ALTER TABLE event_change_requests ADD CONSTRAINT "
        "ck_event_change_requests_rejected_has_reason CHECK (status <> 'rejected' OR "
        "decision_reason IS NOT NULL)"
    ) in sql
    # Postgres won't let a transaction use an enum value it added, so the additions sit
    # after the columns, between a COMMIT and a new BEGIN.
    commit = sql.index("COMMIT")
    assert sql.index("ADD COLUMN decision_reason") < commit
    for value in ADDED:
        added = f"ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS '{value}'"
        assert commit < sql.index(added) < sql.index("BEGIN", commit)


def test_downgrade_removes_everything_the_upgrade_added(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'change_request_approved'",
        "DELETE FROM notifications WHERE kind = 'change_request_rejected'",
        "DELETE FROM notifications WHERE kind = 'event_rescheduled'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'change_request_raised', 'change_request_withdrawn')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "ALTER TABLE event_change_requests DROP CONSTRAINT "
        "ck_event_change_requests_rejected_has_reason",
        "ALTER TABLE event_change_requests DROP CONSTRAINT "
        "ck_event_change_requests_decided_has_time",
        "ALTER TABLE event_change_requests DROP CONSTRAINT fk_event_change_requests_decided_by",
        "ALTER TABLE event_change_requests DROP COLUMN decision_reason",
        "ALTER TABLE event_change_requests DROP COLUMN decided_by",
        "ALTER TABLE event_change_requests DROP COLUMN decided_at",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "'event_rescheduled')" not in sql


# --------------------------------------------------------------------------
# The model holds the same checks, so the unit suite's database enforces them
# --------------------------------------------------------------------------

DECIDED_AT = datetime(2026, 9, 16, 1, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("status", "decision"),
    [
        pytest.param(ChangeRequestStatus.APPROVED, {}, id="approved-with-no-time"),
        pytest.param(
            ChangeRequestStatus.APPROVED, {"decided_at": DECIDED_AT}, id="approved-with-no-decider"
        ),
        pytest.param(
            ChangeRequestStatus.REJECTED,
            {"decided_at": DECIDED_AT, "decided_by": 3},
            id="rejected-with-no-reason",
        ),
    ],
)
def test_the_database_refuses_a_decision_missing_what_it_needs(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: Callable[..., EventChangeRequest],
    db_session: Session,
    status: ChangeRequestStatus,
    decision: dict[str, Any],
) -> None:
    change_request = save_change_request(saved_event_request)
    change_request.status = status
    for column, value in decision.items():
        setattr(change_request, column, value)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_database_accepts_an_approval_with_no_reason(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: Callable[..., EventChangeRequest],
    db_session: Session,
) -> None:
    change_request = save_change_request(saved_event_request)
    change_request.status = ChangeRequestStatus.APPROVED
    change_request.decided_at = DECIDED_AT
    change_request.decided_by = 3

    db_session.commit()

    db_session.expire_all()
    assert db_session.get(EventChangeRequest, change_request.id).decision_reason is None
