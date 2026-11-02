"""Unit tests for migration 0054, which stores SCRUM-70's suggested alternative.

``venue_booking_requests`` gains the alternative Venue Staff may suggest when they
reject a request (AC1, ADR-0123): another venue, another period, or both. All three
columns are nullable, a period is whole or absent, and it ends after it starts. The
model-level tests store a suggestion for real on SQLite; the migration's SQL is
rendered for Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import ModuleType

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.venue.models import Venue, VenueBookingRequest
from tests.venue.conftest import SavedEvent, at, raise_booking, reload_request

pytestmark = pytest.mark.scrum_70

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0054_add_suggested_alternative.py"


def _saved_request(db_session: Session, venue: Venue, saved_event: SavedEvent) -> int:
    return raise_booking(venue, saved_event(), db_session).id


# --------------------------------------------------------------------------
# The model: no suggestion until one is given, and UTC on the way back
# --------------------------------------------------------------------------


def test_a_request_has_no_suggestion_until_one_is_given(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    request = reload_request(db_session, _saved_request(db_session, venue, saved_event))

    assert request.suggested_venue_id is None
    assert request.suggested_starts_at is None
    assert request.suggested_ends_at is None


def test_a_suggestion_given_in_business_time_is_stored_and_read_back_in_utc(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    request_id = _saved_request(db_session, venue, saved_event)
    venue_id = venue.id
    request = reload_request(db_session, request_id)
    request.suggested_venue_id = venue_id
    request.suggested_starts_at = at(9, day=3)
    request.suggested_ends_at = at(12, day=3)

    db_session.commit()
    # A fresh copy, so nothing set on the one above can be read back by mistake.
    db_session.expunge_all()

    stored = reload_request(db_session, request_id)
    assert stored.suggested_venue_id == venue_id
    assert stored.suggested_starts_at == datetime(2026, 11, 3, 1, 0, tzinfo=UTC)
    assert stored.suggested_ends_at == datetime(2026, 11, 3, 4, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("starts_at", "ends_at"),
    [
        pytest.param(at(9, day=3), None, id="a start with no end"),
        pytest.param(None, at(12, day=3), id="an end with no start"),
        pytest.param(at(12, day=3), at(9, day=3), id="an end before the start"),
        pytest.param(at(9, day=3), at(9, day=3), id="an end at the start"),
    ],
)
def test_the_database_refuses_a_suggested_period_that_is_not_a_whole_period(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    starts_at: datetime | None,
    ends_at: datetime | None,
) -> None:
    request = db_session.get(VenueBookingRequest, _saved_request(db_session, venue, saved_event))
    assert request is not None
    request.suggested_starts_at = starts_at
    request.suggested_ends_at = ends_at

    with pytest.raises(IntegrityError):
        db_session.commit()


# --------------------------------------------------------------------------
# The migration: the same columns and rules for Postgres, after 0053
# --------------------------------------------------------------------------


def test_the_migration_follows_the_change_requests_migration(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)

    assert migration.revision == "0054_add_suggested_alternative"
    assert migration.down_revision == "0053_create_change_requests"
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(migration.revision) <= 32


def test_upgrade_adds_the_nullable_columns_the_foreign_key_and_the_period_rules(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "ALTER TABLE venue_booking_requests ADD COLUMN suggested_venue_id INTEGER;",
        "ALTER TABLE venue_booking_requests ADD COLUMN suggested_starts_at "
        "TIMESTAMP WITH TIME ZONE;",
        "ALTER TABLE venue_booking_requests ADD COLUMN suggested_ends_at TIMESTAMP WITH TIME ZONE;",
        "ALTER TABLE venue_booking_requests ADD CONSTRAINT "
        "fk_venue_booking_requests_suggested_venue_id FOREIGN KEY(suggested_venue_id) "
        "REFERENCES venues (id)",
        "ALTER TABLE venue_booking_requests ADD CONSTRAINT "
        "ck_venue_booking_requests_suggestion_period_whole "
        "CHECK ((suggested_starts_at IS NULL) = (suggested_ends_at IS NULL))",
        "ALTER TABLE venue_booking_requests ADD CONSTRAINT "
        "ck_venue_booking_requests_suggestion_ends_after_start "
        "CHECK (suggested_ends_at > suggested_starts_at)",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_drops_the_rules_the_foreign_key_and_the_columns(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "ALTER TABLE venue_booking_requests DROP CONSTRAINT "
        "ck_venue_booking_requests_suggestion_ends_after_start",
        "ALTER TABLE venue_booking_requests DROP CONSTRAINT "
        "ck_venue_booking_requests_suggestion_period_whole",
        "ALTER TABLE venue_booking_requests DROP CONSTRAINT "
        "fk_venue_booking_requests_suggested_venue_id",
        "ALTER TABLE venue_booking_requests DROP COLUMN suggested_ends_at",
        "ALTER TABLE venue_booking_requests DROP COLUMN suggested_starts_at",
        "ALTER TABLE venue_booking_requests DROP COLUMN suggested_venue_id",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
