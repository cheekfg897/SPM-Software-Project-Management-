"""Unit tests for migration 0031, which adds SCRUM-53's withdrawn registrations.

It adds ``withdrawn`` to ``registration_status`` and a ``withdrawn_at`` column to
``registrations``. ``flask db check`` doesn't compare enum members, so the value lists
are checked against the model, and the SQL is rendered for Postgres offline so the
upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.registration.models import RegistrationStatus

pytestmark = pytest.mark.scrum_53

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0031_add_withdrawn_registrations.py"


def test_the_model_has_the_previous_and_the_added_values(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)
    previous = set(migration.PREVIOUS_STATUS_VALUES)
    added = set(migration.ADDED_STATUS_VALUES)

    assert previous == {"registered"}
    assert previous | added == {status.value for status in RegistrationStatus}


def test_the_revision_id_fits_alembics_version_column(load_migration: LoadMigration) -> None:
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(load_migration(MIGRATION).revision) <= 32


def test_upgrade_adds_the_column_then_the_value_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "ALTER TABLE registrations ADD COLUMN withdrawn_at TIMESTAMP WITH TIME ZONE",
        "COMMIT",
        "ALTER TYPE registration_status ADD VALUE IF NOT EXISTS 'withdrawn'",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_deletes_the_withdrawn_rows_and_rebuilds_the_type(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM registrations WHERE status = 'withdrawn'",
        "DROP COLUMN withdrawn_at",
        "ALTER TYPE registration_status RENAME TO registration_status_old",
        "CREATE TYPE registration_status AS ENUM ('registered')",
        "ALTER TABLE registrations ALTER COLUMN status "
        "TYPE registration_status USING status::text::registration_status",
        "DROP TYPE registration_status_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
