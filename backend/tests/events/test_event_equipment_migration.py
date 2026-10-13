"""Unit tests for migration 0011, which adds SCRUM-37's equipment lines (ADR-0019).

``flask db check`` doesn't compare enum members, so these tests check the migration's
value lists against the models: the new line status type, and the notification kind
it adds for AC5. They also render the migration's SQL for Postgres offline, so the
upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EquipmentLineStatus
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_37

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0011_create_event_equipment_lines_table.py"


def test_migration_and_model_agree_on_the_line_status_values(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)

    # Subset, not equality: a later migration (SCRUM-48) adds the outcome statuses this
    # migration doesn't know about.
    assert set(migration.LINE_STATUS_VALUES) <= {status.value for status in EquipmentLineStatus}


def test_migration_and_model_agree_on_the_notification_kinds(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    previous = set(migration.PREVIOUS_KIND_VALUES)
    added = set(migration.ADDED_KIND_VALUES)

    # Subset, not equality: a later migration (SCRUM-33) adds more kinds this
    # migration doesn't know about.
    assert previous | added <= {kind.value for kind in NotificationKind}
    assert previous.isdisjoint(added)


def test_the_previous_kinds_are_what_exists_after_migration_0010(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    notifications_migration = load_migration("0009_create_notifications_table.py")
    assignment_migration = load_migration("0010_add_coordinator_assignment_and_event_history.py")
    after_0010 = set(notifications_migration.KIND_VALUES) | set(
        assignment_migration.ADDED_NOTIFICATION_KIND_VALUES
    )

    assert set(migration.PREVIOUS_KIND_VALUES) == after_0010


def test_upgrade_creates_the_table_then_adds_the_kind_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert "CREATE TYPE event_equipment_line_status AS ENUM ('requested')" in sql
    assert "CREATE TABLE event_equipment_lines" in sql
    assert "CONSTRAINT ck_event_equipment_lines_quantity_min CHECK (quantity >= 1)" in sql
    assert (
        "CONSTRAINT uq_event_equipment_lines_event_request_id_equipment_type_id "
        "UNIQUE (event_request_id, equipment_type_id)"
    ) in sql
    assert "ALTER TYPE notification_kind ADD VALUE 'equipment_requested'" in sql
    # Postgres won't let a transaction use an enum value it added, so the addition
    # sits between a COMMIT and a new BEGIN, after the table is created.
    assert sql.index("CREATE TABLE") < sql.index("COMMIT") < sql.index("ADD VALUE")
    assert sql.index("ADD VALUE") < sql.index("BEGIN")


def test_downgrade_drops_the_table_and_rebuilds_notification_kind_without_the_new_value(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'equipment_requested'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted', 'coordinator_assigned')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "DROP TABLE event_equipment_lines",
        "DROP TYPE event_equipment_line_status",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
