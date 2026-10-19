"""Unit tests for migration 0042, which adds SCRUM-69 AC6's withdrawal cut-off.

``event_requests`` gains ``withdrawal_cut_off``, a nullable instant: empty until the
assigned coordinator records one, and empty again when they clear it (ADR-0086). The
model-level tests store a value for real on SQLite; the migration's SQL is rendered
for Postgres offline, so the upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from types import ModuleType

import pytest

from app.modules.auth.models import User
from app.modules.events.models import EventRequest

pytestmark = pytest.mark.scrum_69

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
Save = Callable[..., None]
ReloadEventRequest = Callable[[int], EventRequest]

MIGRATION = "0042_add_withdrawal_cut_off.py"

#: 18:00 in Singapore the evening before ``saved_event_request`` starts.
CUT_OFF = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# The model: no cut-off until one is recorded, and UTC on the way back
# --------------------------------------------------------------------------


def test_a_request_has_no_withdrawal_cut_off_until_one_is_recorded(
    saved_users: list[User],
    saved_event_request: EventRequest,
    reload_event_request: ReloadEventRequest,
) -> None:
    assert reload_event_request(saved_event_request.id).withdrawal_cut_off is None


def test_a_cut_off_given_in_business_time_is_stored_and_read_back_in_utc(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Save,
    reload_event_request: ReloadEventRequest,
) -> None:
    singapore = timezone(timedelta(hours=8))
    saved_event_request.withdrawal_cut_off = CUT_OFF.astimezone(singapore)

    save(saved_event_request)

    stored = reload_event_request(saved_event_request.id).withdrawal_cut_off
    assert stored == CUT_OFF
    assert stored is not None
    assert stored.tzinfo == timezone.utc


# --------------------------------------------------------------------------
# The migration: renders the same column for Postgres, after main's head
# --------------------------------------------------------------------------


def test_the_migration_follows_the_previous_head(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.revision == "0042_add_withdrawal_cut_off"
    assert migration.down_revision == "0041_add_booking_conflicting"


def test_the_revision_id_fits_alembics_version_column(load_migration: LoadMigration) -> None:
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(load_migration(MIGRATION).revision) <= 32


def test_upgrade_adds_a_nullable_instant_column(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert (
        "ALTER TABLE event_requests ADD COLUMN withdrawal_cut_off TIMESTAMP WITH TIME ZONE;"
    ) in sql


def test_downgrade_drops_the_column(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.downgrade)

    assert "ALTER TABLE event_requests DROP COLUMN withdrawal_cut_off" in sql
