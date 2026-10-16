"""Unit tests for migration 0029, SCRUM-97's role, status and history kind (ADR-0047).

``user_role`` gains ``safety_officer`` (AC7), ``event_request_status`` gains
``safety_review`` (AC1) and ``event_history_entry_kind`` gains
``safety_review_requested``. ``flask db check`` doesn't compare enum members, so these
tests check the migration's value lists against the models and the migrations below
it, and render its SQL for Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.auth.permissions import Role
from app.modules.events.models import EventHistoryKind, EventRequestStatus

pytestmark = pytest.mark.scrum_97

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
AssertMigrationAndModelAgree = Callable[[tuple[str, ...], tuple[str, ...], set[str]], None]

MIGRATION = "0029_add_safety_review.py"


@pytest.mark.parametrize(
    ("below", "previous", "added_below"),
    [
        ("0022_add_event_coordinator_lead_role.py", "PREVIOUS_ROLE_VALUES", "ADDED_ROLE_VALUES"),
        (
            "0018_add_clarification_status_and_kinds.py",
            "PREVIOUS_STATUS_VALUES",
            "ADDED_STATUS_VALUES",
        ),
        (
            "0025_add_booking_request_decisions.py",
            "PREVIOUS_HISTORY_KIND_VALUES",
            "ADDED_HISTORY_KIND_VALUES",
        ),
    ],
)
def test_each_previous_list_is_what_the_last_migration_to_change_it_left(
    load_migration: LoadMigration, below: str, previous: str, added_below: str
) -> None:
    migration = load_migration(MIGRATION)
    last = load_migration(below)
    # In Postgres's order: each ADD VALUE appends.
    left_by_last = (*getattr(last, previous), *getattr(last, added_below))

    assert getattr(migration, previous) == left_by_last


def test_migration_and_models_agree(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_ROLE_VALUES, migration.ADDED_ROLE_VALUES, set(Role.values())
    )
    assert_migration_and_model_agree(
        migration.PREVIOUS_STATUS_VALUES,
        migration.ADDED_STATUS_VALUES,
        {status.value for status in EventRequestStatus},
    )
    assert_migration_and_model_agree(
        migration.PREVIOUS_HISTORY_KIND_VALUES,
        migration.ADDED_HISTORY_KIND_VALUES,
        {kind.value for kind in EventHistoryKind},
    )
    assert migration.down_revision == "0028_add_conflicting_status"


def test_upgrade_adds_the_three_values_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    add_role = "ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'safety_officer'"
    add_status = "ALTER TYPE event_request_status ADD VALUE IF NOT EXISTS 'safety_review'"
    add_kind = (
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'safety_review_requested'"
    )
    # Postgres won't let a transaction use an enum value it added, so the additions sit
    # between a COMMIT and a new BEGIN.
    assert (
        sql.index("COMMIT")
        < sql.index(add_role)
        < sql.index(add_status)
        < sql.index(add_kind)
        < sql.index("BEGIN")
    )


def test_downgrade_moves_rows_off_the_new_values_then_rebuilds_each_type(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(
        sql,
        [
            "DELETE FROM event_history_entries WHERE kind = 'safety_review_requested'",
            "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
            "DROP TYPE event_history_entry_kind_old",
            "UPDATE event_requests SET status = 'approved' WHERE status = 'safety_review'",
            "ALTER TYPE event_request_status RENAME TO event_request_status_old",
            "CREATE TYPE event_request_status AS ENUM ('submitted', 'draft', 'under_review', "
            "'confirmed', 'completed', 'cancelled', 'rejected', 'approved', "
            "'awaiting_clarification')",
            "ALTER TABLE event_requests DROP CONSTRAINT ck_event_requests_details_unless_draft",
            "ALTER TABLE event_requests ALTER COLUMN status "
            "TYPE event_request_status USING status::text::event_request_status",
            "ALTER TABLE event_requests ADD CONSTRAINT ck_event_requests_details_unless_draft",
            "DROP TYPE event_request_status_old",
            "UPDATE users SET role = 'attendee' WHERE role = 'safety_officer'",
            "ALTER TYPE user_role RENAME TO user_role_old",
            "DROP TYPE user_role_old",
        ],
    )
