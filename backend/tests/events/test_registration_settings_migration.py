"""Unit tests for migration 0026, which adds SCRUM-69's registration settings.

``event_requests`` gains ``registration_enabled`` (not null, false until enabled) and
``registration_capacity`` (null until set), and a check constraint for each rule the
database keeps: a capacity of at least 1, and a capacity for every enabled event
(ADR-0043). The model-level tests run the constraints for real on SQLite; the
migration's SQL is rendered for Postgres offline, so the upgrade and the downgrade are
tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, time
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models import User
from app.modules.events.models import EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_69

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
Save = Callable[..., None]
ReloadEventRequest = Callable[[int], EventRequest]

MIGRATION = "0026_add_event_registration_settings.py"
CAPACITY_CHECK = "ck_event_requests_registration_capacity_min"
ENABLED_CHECK = "ck_event_requests_enabled_registration_has_capacity"


def _make_request(**settings: Any) -> EventRequest:
    """A confirmed request with a fixed identity, only its settings varying."""
    return EventRequest(
        reference="EVR-AAAAAAAA",
        status=EventRequestStatus.CONFIRMED,
        organiser_id=7,
        organisation_id=3,
        name="Partner Summit",
        proposed_date=date(2026, 10, 15),
        end_date=date(2026, 10, 15),
        start_time=time(9, 0),
        end_time=time(17, 0),
        expected_attendance=250,
        registration_required=False,
        **settings,
    )


# --------------------------------------------------------------------------
# The model: the settings and the rules the database keeps
# --------------------------------------------------------------------------


def test_a_new_request_has_registration_disabled_and_no_capacity(
    saved_users: list[User], save: Save, reload_event_request: ReloadEventRequest
) -> None:
    request = _make_request()

    save(request)

    reloaded = reload_event_request(request.id)
    assert (reloaded.registration_enabled, reloaded.registration_capacity) == (False, None)


def test_the_database_accepts_an_enabled_request_with_a_capacity_of_one(
    saved_users: list[User], save: Save, reload_event_request: ReloadEventRequest
) -> None:
    request = _make_request(registration_enabled=True, registration_capacity=1)

    save(request)

    reloaded = reload_event_request(request.id)
    assert (reloaded.registration_enabled, reloaded.registration_capacity) == (True, 1)


def test_the_database_accepts_a_capacity_while_registration_is_disabled(
    saved_users: list[User], save: Save, reload_event_request: ReloadEventRequest
) -> None:
    request = _make_request(registration_enabled=False, registration_capacity=50)

    save(request)

    assert reload_event_request(request.id).registration_capacity == 50


@pytest.mark.parametrize("capacity", [0, -1])
def test_the_database_refuses_a_capacity_below_one(
    saved_users: list[User], save: Save, capacity: int
) -> None:
    request = _make_request(registration_capacity=capacity)

    with pytest.raises(IntegrityError, match=CAPACITY_CHECK):
        save(request)


def test_the_database_refuses_enabled_registration_without_a_capacity(
    saved_users: list[User], save: Save
) -> None:
    request = _make_request(registration_enabled=True)

    with pytest.raises(IntegrityError, match=ENABLED_CHECK):
        save(request)


# --------------------------------------------------------------------------
# The migration: renders the same columns and rules for Postgres
# --------------------------------------------------------------------------


def test_upgrade_adds_the_two_columns(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert (
        "ALTER TABLE event_requests ADD COLUMN registration_enabled BOOLEAN DEFAULT false NOT NULL"
    ) in sql
    assert "ALTER TABLE event_requests ADD COLUMN registration_capacity INTEGER" in sql


def test_upgrade_adds_the_two_check_constraints(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert f"CONSTRAINT {CAPACITY_CHECK} CHECK (registration_capacity >= 1)" in sql
    assert (
        f"CONSTRAINT {ENABLED_CHECK} CHECK "
        "(NOT registration_enabled OR registration_capacity IS NOT NULL)"
    ) in sql


def test_downgrade_drops_the_constraints_before_the_columns(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        f"ALTER TABLE event_requests DROP CONSTRAINT {ENABLED_CHECK}",
        f"ALTER TABLE event_requests DROP CONSTRAINT {CAPACITY_CHECK}",
        "ALTER TABLE event_requests DROP COLUMN registration_capacity",
        "ALTER TABLE event_requests DROP COLUMN registration_enabled",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
