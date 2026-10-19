"""Unit tests for migration 0043, SCRUM-33 AC6's reassessment flags (ADR-0094).

It adds the ``reassessment_flag_kind`` type and the ``reassessment_flags`` table.
``flask db check`` doesn't compare enum members, so these tests check the migration's
values against the model, and render its SQL for Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.venue.models import ReassessmentFlagKind

pytestmark = pytest.mark.scrum_33

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0043_add_reassessment_flags.py"


def test_it_follows_the_withdrawal_cut_off_migration(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.down_revision == "0042_add_withdrawal_cut_off"
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(migration.revision) <= 32


def test_the_migrations_values_are_the_models_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    model_values = tuple(kind.value for kind in ReassessmentFlagKind)

    assert model_values == migration.FLAG_KIND_VALUES


def test_upgrade_creates_the_type_then_the_table(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "CREATE TYPE reassessment_flag_kind AS ENUM "
        "('requires_reconfirmation', 'no_longer_suitable')",
        "CREATE TABLE reassessment_flags",
        "kind reassessment_flag_kind NOT NULL",
        "FOREIGN KEY(booking_request_id) REFERENCES venue_booking_requests (id) ON DELETE CASCADE",
        "CREATE INDEX ix_reassessment_flags_booking_request_id ON reassessment_flags "
        "(booking_request_id)",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_drops_the_table_then_the_type(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DROP INDEX ix_reassessment_flags_booking_request_id",
        "DROP TABLE reassessment_flags",
        "DROP TYPE reassessment_flag_kind",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
