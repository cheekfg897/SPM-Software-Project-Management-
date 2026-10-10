"""Unit tests for migration 0021, which holds SCRUM-46's reservations (ADR-0037).

It creates ``equipment_reservations`` and ``equipment_out_of_service`` with the
``out_of_service_reason`` enum, and adds ``equipment_reserved`` to ``notification_kind``
(AC5) and ``event_history_entry_kind`` (the audit trail). ``flask db check`` doesn't
compare enum members, so these tests check the migration's value lists against the
model and the migrations below it, and render its SQL for Postgres offline so the
upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.equipment.models import OutOfServiceReason
from app.modules.events.models import EventHistoryKind
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_46

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0021_add_equipment_reservations.py"
#: The last migrations to change ``event_history_entry_kind`` and ``notification_kind``.
HISTORY_MIGRATION_BELOW = "0018_add_clarification_status_and_kinds.py"
NOTIFICATION_MIGRATION_BELOW = "0019_add_review_notification_kinds.py"


def test_the_previous_history_kinds_are_what_exists_after_the_migration_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(HISTORY_MIGRATION_BELOW)
    after_below = set(below.PREVIOUS_HISTORY_KIND_VALUES) | set(below.ADDED_HISTORY_KIND_VALUES)

    assert set(migration.PREVIOUS_HISTORY_KIND_VALUES) == after_below


def test_the_previous_notification_kinds_are_what_exists_after_the_migration_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(NOTIFICATION_MIGRATION_BELOW)
    after_below = set(below.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(
        below.ADDED_NOTIFICATION_KIND_VALUES
    )

    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) == after_below


def test_migration_and_model_agree_on_the_enums(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    # Subset, not equality: a later migration could add a further kind this one doesn't
    # know about.
    history = set(migration.PREVIOUS_HISTORY_KIND_VALUES) | set(migration.ADDED_HISTORY_KIND_VALUES)
    notifications = set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(
        migration.ADDED_NOTIFICATION_KIND_VALUES
    )
    assert history <= {kind.value for kind in EventHistoryKind}
    assert notifications <= {kind.value for kind in NotificationKind}
    assert migration.ADDED_HISTORY_KIND_VALUES == ("equipment_reserved",)
    assert migration.ADDED_NOTIFICATION_KIND_VALUES == ("equipment_reserved",)
    assert set(migration.OUT_OF_SERVICE_REASON_VALUES) == {
        reason.value for reason in OutOfServiceReason
    }


def test_upgrade_creates_both_tables_and_adds_the_kinds_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(
        sql,
        [
            "CREATE TYPE out_of_service_reason AS ENUM ('damaged', 'under_maintenance')",
            "CREATE TABLE equipment_reservations",
            "CREATE TABLE equipment_out_of_service",
            "COMMIT",
            "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'equipment_reserved'",
            "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'equipment_reserved'",
            "BEGIN",
        ],
    )
    assert "ck_equipment_reservations_quantity_min CHECK (quantity >= 1)" in sql
    assert "ck_equipment_out_of_service_quantity_min CHECK (quantity >= 1)" in sql


def test_downgrade_drops_the_tables_and_the_reason_type_then_rebuilds_both_kind_types(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(
        sql,
        [
            "DELETE FROM notifications WHERE kind = 'equipment_reserved'",
            "ALTER TYPE notification_kind RENAME TO notification_kind_old",
            "DROP TYPE notification_kind_old",
            "DELETE FROM event_history_entries WHERE kind = 'equipment_reserved'",
            "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
            "DROP TYPE event_history_entry_kind_old",
            "DROP TABLE equipment_out_of_service",
            "DROP TABLE equipment_reservations",
            "DROP TYPE out_of_service_reason",
        ],
    )
