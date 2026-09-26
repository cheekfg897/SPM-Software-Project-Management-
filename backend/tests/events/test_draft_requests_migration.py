"""Unit tests for migration 0014, which lets a draft leave its details empty.

SCRUM-20 "Save and resume a draft event request" AC1 (ADR-0024): the five columns
that describe when and how big an event is (``proposed_date``, ``end_date``,
``start_time``, ``end_time``, ``expected_attendance``) become nullable, and a check
constraint requires them all once a request leaves the draft stage. The migration's
SQL is rendered for Postgres offline, so the upgrade and the downgrade are tested
without a database; the model-level tests run the constraint for real on SQLite.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, time
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events.models import EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_20

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
Save = Callable[..., None]

MIGRATION = "0014_allow_incomplete_draft_requests.py"
CHECK_NAME = "ck_event_requests_details_unless_draft"
CHECK_CONDITION = (
    "status = 'draft' OR (proposed_date IS NOT NULL AND end_date IS NOT NULL AND "
    "start_time IS NOT NULL AND end_time IS NOT NULL AND expected_attendance IS NOT NULL)"
)

#: The five columns a draft may leave empty (ADR-0024).
DETAIL_COLUMNS = ["proposed_date", "end_date", "start_time", "end_time", "expected_attendance"]


def _full_details(**overrides: Any) -> dict[str, Any]:
    """Every detail column filled in with a valid value, so a test can knock one out."""
    values: dict[str, Any] = {
        "proposed_date": date(2026, 10, 15),
        "end_date": date(2026, 10, 15),
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "expected_attendance": 250,
    }
    values.update(overrides)
    return values


def _make_request(status: EventRequestStatus, **detail_overrides: Any) -> EventRequest:
    """An event request with a fixed identity, only the status and details varying."""
    return EventRequest(
        reference="EVR-AAAAAAAA",
        status=status,
        organiser_id=7,
        organisation_id=3,
        name="Partner Summit",
        registration_required=False,
        **_full_details(**detail_overrides),
    )


# --------------------------------------------------------------------------
# The model: the five columns are nullable, guarded by the check constraint
# --------------------------------------------------------------------------


def test_the_model_lets_only_a_draft_leave_its_details_empty() -> None:
    columns = {column.name: column for column in EventRequest.__table__.columns}
    for name in DETAIL_COLUMNS:
        assert columns[name].nullable is True, f"{name} should be nullable"

    constraint_names = {constraint.name for constraint in EventRequest.__table__.constraints}
    assert CHECK_NAME in constraint_names


def test_the_database_accepts_a_draft_with_only_its_name(
    db_session: Session, saved_users: list[User], save: Save
) -> None:
    draft = EventRequest(
        reference="EVR-DDDDDDDD",
        status=EventRequestStatus.DRAFT,
        organiser_id=7,
        organisation_id=3,
        name="Just an idea",
        registration_required=False,
    )

    save(draft)
    db_session.expire_all()
    reloaded = db_session.get(EventRequest, draft.id)

    assert reloaded is not None
    for column in DETAIL_COLUMNS:
        assert getattr(reloaded, column) is None


@pytest.mark.parametrize("column", DETAIL_COLUMNS)
def test_the_database_refuses_a_request_past_the_draft_stage_without_its_details(
    saved_users: list[User], save: Save, column: str
) -> None:
    request = _make_request(EventRequestStatus.SUBMITTED, **{column: None})

    with pytest.raises(IntegrityError):
        save(request)


# --------------------------------------------------------------------------
# The migration: renders the same rules for Postgres
# --------------------------------------------------------------------------


@pytest.mark.parametrize("column", DETAIL_COLUMNS)
def test_upgrade_drops_not_null_from_the_event_details(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql, column: str
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert f"ALTER TABLE event_requests ALTER COLUMN {column} DROP NOT NULL" in sql


def test_upgrade_requires_the_details_unless_a_draft(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert f"CONSTRAINT {CHECK_NAME} CHECK ({CHECK_CONDITION})" in sql


def test_downgrade_deletes_incomplete_drafts_before_restoring_not_null(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        f"ALTER TABLE event_requests DROP CONSTRAINT {CHECK_NAME}",
        "DELETE FROM event_requests WHERE status = 'draft' AND (",
        "ALTER TABLE event_requests ALTER COLUMN proposed_date SET NOT NULL",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
