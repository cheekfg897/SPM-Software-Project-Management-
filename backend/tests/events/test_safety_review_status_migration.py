"""Unit tests for migration 0028, which adds the ``safety_review`` status (ADR-0045).

``flask db check`` doesn't compare enum members, so these tests check the migration's
value lists against the model and against migration 0018, which it builds on, and
render its SQL for Postgres offline so the upgrade and the downgrade are tested
without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventRequestStatus

pytestmark = pytest.mark.scrum_22

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
AssertMigrationAndModelAgree = Callable[[tuple[str, ...], tuple[str, ...], set[str]], None]

MIGRATION = "0028_add_safety_review_status.py"
CLARIFICATION_MIGRATION = "0018_add_clarification_status_and_kinds.py"
DRAFTS_MIGRATION = "0014_allow_incomplete_draft_requests.py"


def test_the_previous_statuses_are_what_exists_after_migration_0018_in_postgres_order(
    load_migration: LoadMigration,
) -> None:
    previous = load_migration(MIGRATION).PREVIOUS_STATUS_VALUES
    clarification = load_migration(CLARIFICATION_MIGRATION)
    after_0018 = clarification.PREVIOUS_STATUS_VALUES + clarification.ADDED_STATUS_VALUES

    # A tuple, not a set: downgrade rebuilds the type in this order.
    assert previous == after_0018


def test_migration_and_model_agree_on_the_status_values(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_STATUS_VALUES,
        migration.ADDED_STATUS_VALUES,
        {status.value for status in EventRequestStatus},
    )


def test_upgrade_adds_safety_review_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert "ALTER TYPE event_request_status ADD VALUE IF NOT EXISTS 'safety_review'" in sql
    # Postgres won't let a transaction use an enum value it added, so the addition
    # sits between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index("ADD VALUE")
    assert sql.rindex("ADD VALUE") < sql.index("BEGIN")
    assert "ADD COLUMN" not in sql


def test_downgrade_returns_events_in_safety_review_to_approved_and_rebuilds_the_type(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    # The check 0014 added, that a request past the draft stage has its details,
    # compares the status, so it would stop the column changing type.
    drafts = load_migration(DRAFTS_MIGRATION)
    expected_in_order = [
        "UPDATE event_requests SET status = 'approved' WHERE status = 'safety_review'",
        "ALTER TYPE event_request_status RENAME TO event_request_status_old",
        "CREATE TYPE event_request_status AS ENUM ('submitted', 'draft', 'under_review', "
        "'confirmed', 'completed', 'cancelled', 'rejected', 'approved', "
        "'awaiting_clarification')",
        f"ALTER TABLE event_requests DROP CONSTRAINT {drafts.CHECK_NAME}",
        "ALTER TABLE event_requests ALTER COLUMN status "
        "TYPE event_request_status USING status::text::event_request_status",
        f"ALTER TABLE event_requests ADD CONSTRAINT {drafts.CHECK_NAME} "
        f"CHECK ({drafts.CHECK_CONDITION})",
        "DROP TYPE event_request_status_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
