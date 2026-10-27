"""Unit tests for migration 0050, which marks a reservation for reassessment (SCRUM-60).

``equipment_reservations`` gains ``needs_reassessment``: false until a change to the
event's date or time, or to its line's quantity, marks the reservation, and false again
once Technical Support settle it (ADR-0114). The model-level test stores a reservation
for real on SQLite; the migration's SQL is rendered for Postgres offline, so the
upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentReservation, EquipmentType

pytestmark = pytest.mark.scrum_60

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
MakeReservation = Callable[[EquipmentType, int, datetime, datetime], EquipmentReservation]

MIGRATION = "0050_add_needs_reassessment.py"

STARTS_AT = datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)


def test_a_new_reservation_does_not_need_reassessment(
    db_session: Session,
    equipment_type: EquipmentType,
    make_reservation: MakeReservation,
    save: Callable[..., None],
) -> None:
    save(make_reservation(equipment_type, 2, STARTS_AT, ENDS_AT))

    db_session.expire_all()
    assert db_session.scalars(select(EquipmentReservation)).one().needs_reassessment is False


def test_the_migration_revises_0049_and_its_id_fits_alembics_column(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)

    assert migration.revision == "0050_add_needs_reassessment"
    assert migration.down_revision == "0049_add_booking_reconfirmed"
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(migration.revision) <= 32


def test_upgrade_adds_a_column_that_is_false_for_existing_reservations(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    sql = render_migration_sql(load_migration(MIGRATION).upgrade)

    assert (
        "ALTER TABLE equipment_reservations ADD COLUMN needs_reassessment BOOLEAN"
        " DEFAULT false NOT NULL;"
    ) in sql


def test_downgrade_drops_the_column(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    sql = render_migration_sql(load_migration(MIGRATION).downgrade)

    assert "ALTER TABLE equipment_reservations DROP COLUMN needs_reassessment" in sql
