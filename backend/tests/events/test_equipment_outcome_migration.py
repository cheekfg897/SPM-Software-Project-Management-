"""Unit tests for migration 0024, SCRUM-48's equipment review outcome.

It adds the outcome columns to ``event_equipment_lines``, three values to
``event_equipment_line_status`` and ``equipment_outcome_recorded`` to
``event_history_entry_kind`` and ``notification_kind``. ``flask db check`` doesn't
compare enum members, so these tests check the migration's value lists against the
models and the migrations below it, and render its SQL for Postgres offline so the
upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EquipmentLineStatus, EventHistoryKind
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_48

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
AssertMigrationAndModelAgree = Callable[[tuple[str, ...], tuple[str, ...], set[str]], None]

MIGRATION = "0024_add_equipment_review_outcome.py"
#: The last migrations to change ``event_history_entry_kind`` and ``notification_kind``.
HISTORY_MIGRATION_BELOW = "0023_add_withdrawn_arrangements.py"
NOTIFICATION_MIGRATION_BELOW = "0022_add_event_coordinator_lead_role.py"


def test_the_previous_kinds_are_what_exists_after_the_migrations_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    history_below = load_migration(HISTORY_MIGRATION_BELOW)
    notification_below = load_migration(NOTIFICATION_MIGRATION_BELOW)
    history_after_below = set(history_below.PREVIOUS_HISTORY_KIND_VALUES) | set(
        history_below.ADDED_HISTORY_KIND_VALUES
    )
    notifications_after_below = set(notification_below.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(
        notification_below.ADDED_NOTIFICATION_KIND_VALUES
    )

    assert set(migration.PREVIOUS_HISTORY_KIND_VALUES) == history_after_below
    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) == notifications_after_below


def test_migration_and_models_agree_on_the_new_values(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_LINE_STATUS_VALUES,
        migration.ADDED_LINE_STATUS_VALUES,
        {status.value for status in EquipmentLineStatus},
    )
    assert_migration_and_model_agree(
        migration.PREVIOUS_HISTORY_KIND_VALUES,
        migration.ADDED_HISTORY_KIND_VALUES,
        {kind.value for kind in EventHistoryKind},
    )
    assert_migration_and_model_agree(
        migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        migration.ADDED_NOTIFICATION_KIND_VALUES,
        {kind.value for kind in NotificationKind},
    )


def test_the_revision_id_fits_alembics_version_column(load_migration: LoadMigration) -> None:
    # alembic_version.version_num is VARCHAR(32); a longer id fails only on Postgres.
    assert len(load_migration(MIGRATION).revision) <= 32


def test_upgrade_adds_the_columns_then_the_values_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "ALTER TABLE event_equipment_lines ADD COLUMN provided_quantity INTEGER",
        "ALTER TABLE event_equipment_lines ADD COLUMN outcome_note TEXT",
        "ALTER TABLE event_equipment_lines ADD COLUMN reviewed_by INTEGER",
        "ALTER TABLE event_equipment_lines ADD COLUMN reviewed_at TIMESTAMP WITH TIME ZONE",
        "ADD CONSTRAINT ck_event_equipment_lines_provided_within_quantity CHECK "
        "(provided_quantity IS NULL OR provided_quantity BETWEEN 0 AND quantity)",
        "COMMIT",
        "ALTER TYPE event_equipment_line_status ADD VALUE IF NOT EXISTS 'fulfilled'",
        "ALTER TYPE event_equipment_line_status ADD VALUE IF NOT EXISTS 'partially_fulfilled'",
        "ALTER TYPE event_equipment_line_status ADD VALUE IF NOT EXISTS 'unavailable'",
        "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'equipment_outcome_recorded'",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'equipment_outcome_recorded'",
        "BEGIN",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_clears_the_outcomes_and_rebuilds_the_types_without_the_new_values(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "UPDATE event_equipment_lines SET status = 'requested', provided_quantity = NULL",
        "DROP CONSTRAINT ck_event_equipment_lines_provided_within_quantity",
        "DROP COLUMN reviewed_at",
        "DROP COLUMN reviewed_by",
        "DROP COLUMN outcome_note",
        "DROP COLUMN provided_quantity",
        "ALTER TYPE event_equipment_line_status RENAME TO event_equipment_line_status_old",
        "CREATE TYPE event_equipment_line_status AS ENUM ('requested')",
        "ALTER TABLE event_equipment_lines ALTER COLUMN status "
        "TYPE event_equipment_line_status USING status::text::event_equipment_line_status",
        "DROP TYPE event_equipment_line_status_old",
        "DELETE FROM event_history_entries WHERE kind = 'equipment_outcome_recorded'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "DROP TYPE event_history_entry_kind_old",
        "DELETE FROM notifications WHERE kind = 'equipment_outcome_recorded'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
