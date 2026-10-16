"""Unit tests for migration 0030, SCRUM-97's notification kind (ADR-0047).

``notification_kind`` gains ``safety_review_requested`` (AC4). ``flask db check``
doesn't compare enum members, so these tests check the migration's value lists
against the model and the migration below it, and render its SQL for Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_97

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
AssertMigrationAndModelAgree = Callable[[tuple[str, ...], tuple[str, ...], set[str]], None]

MIGRATION = "0030_add_safety_review_notification_kind.py"
#: The last migration to change ``notification_kind`` before this one.
PREVIOUS_MIGRATION = "0025_add_booking_request_decisions.py"


def test_the_previous_kinds_are_what_the_last_migration_to_change_them_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(PREVIOUS_MIGRATION)
    # In Postgres's order: each ADD VALUE appends.
    left_by_below = (
        *below.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *below.ADDED_NOTIFICATION_KIND_VALUES,
    )

    assert left_by_below == migration.PREVIOUS_NOTIFICATION_KIND_VALUES


def test_migration_and_model_agree_and_it_follows_the_safety_review_migration(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        migration.ADDED_NOTIFICATION_KIND_VALUES,
        {kind.value for kind in NotificationKind},
    )
    assert migration.ADDED_NOTIFICATION_KIND_VALUES == ("safety_review_requested",)
    assert migration.down_revision == "0029_add_safety_review"


def test_upgrade_adds_the_value_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    add_kind = "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'safety_review_requested'"
    # Postgres won't let a transaction use an enum value it added, so the addition sits
    # between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index(add_kind) < sql.index("BEGIN")


def test_downgrade_deletes_the_new_notifications_and_rebuilds_the_type_without_the_value(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(PREVIOUS_MIGRATION)
    previous_kinds = ", ".join(
        f"'{kind}'"
        for kind in (
            *below.PREVIOUS_NOTIFICATION_KIND_VALUES,
            *below.ADDED_NOTIFICATION_KIND_VALUES,
        )
    )
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'safety_review_requested'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        f"CREATE TYPE notification_kind AS ENUM ({previous_kinds})",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
