"""Unit tests for migration 0027, which creates SCRUM-52's ``registrations`` table.

A registration is one Attendee's place at one event: the event and the attendee (both
database-level foreign keys only, so the modules stay apart), a status, and when it was
made. The database keeps the rule that an attendee holds one registration per event
(AC3), whatever the service checks. The model-level tests run the constraint for real
on SQLite; the migration's SQL is rendered for Postgres offline, so the upgrade and the
downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.events.models import EventRequest
from app.modules.registration.models import Registration

pytestmark = pytest.mark.scrum_52

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
MakeRegistration = Callable[..., Registration]

MIGRATION = "0027_create_registrations_table.py"
UNIQUE_CONSTRAINT = "uq_registrations_event_request_id_attendee_id"


# --------------------------------------------------------------------------
# The model: one registration per attendee per event
# --------------------------------------------------------------------------


def test_the_database_refuses_a_second_registration_for_the_same_attendee_and_event(
    open_event: EventRequest, make_registration: MakeRegistration
) -> None:
    make_registration(open_event, 21)

    with pytest.raises(IntegrityError, match=r"registrations\.event_request_id"):
        make_registration(open_event, 21)


def test_the_database_accepts_one_registration_each_for_two_attendees_and_two_events(
    make_open_event: Callable[..., EventRequest], make_registration: MakeRegistration
) -> None:
    first = make_open_event(name="First")
    second = make_open_event(name="Second")

    registrations = [
        make_registration(first, 21),
        make_registration(first, 22),
        make_registration(second, 21),
    ]

    assert [registration.id is not None for registration in registrations] == [True] * 3


# --------------------------------------------------------------------------
# The migration: renders the table, its rules and its enum for Postgres
# --------------------------------------------------------------------------


def test_upgrade_creates_the_table_with_its_columns_and_enum(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert "CREATE TYPE registration_status AS ENUM ('registered')" in sql
    assert "CREATE TABLE registrations" in sql
    for column in [
        "event_request_id INTEGER NOT NULL",
        "attendee_id INTEGER NOT NULL",
        "status registration_status NOT NULL",
        "registered_at TIMESTAMP WITH TIME ZONE NOT NULL",
    ]:
        assert column in sql


def test_upgrade_adds_the_foreign_keys_and_the_unique_pair(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert "FOREIGN KEY(event_request_id) REFERENCES event_requests (id)" in sql
    assert "FOREIGN KEY(attendee_id) REFERENCES users (id)" in sql
    assert f"CONSTRAINT {UNIQUE_CONSTRAINT} UNIQUE (event_request_id, attendee_id)" in sql


def test_upgrade_indexes_the_event_and_the_attendee(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert (
        "CREATE INDEX ix_registrations_event_request_id ON registrations (event_request_id)" in sql
    )
    assert "CREATE INDEX ix_registrations_attendee_id ON registrations (attendee_id)" in sql


def test_downgrade_drops_the_indexes_and_table_before_the_enum_type(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DROP INDEX ix_registrations_attendee_id",
        "DROP INDEX ix_registrations_event_request_id",
        "DROP TABLE registrations",
        "DROP TYPE registration_status",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
