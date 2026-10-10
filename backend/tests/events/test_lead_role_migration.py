"""Unit tests for migration 0022, SCRUM-95's role and notification kind (ADR-0036).

``user_role`` gains ``event_coordinator_lead`` (AC7) and ``notification_kind`` gains
``request_queued_for_lead`` (AC4). ``flask db check`` doesn't compare enum members, so
these tests check the migration's value lists against the models and render its SQL for
Postgres offline, so the upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.auth.permissions import Role
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_95

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]
AssertMigrationAndModelAgree = Callable[[tuple[str, ...], tuple[str, ...], set[str]], None]

MIGRATION = "0022_add_event_coordinator_lead_role.py"
#: The last migration to change ``notification_kind`` before this one.
PREVIOUS_MIGRATION = "0019_add_review_notification_kinds.py"


def test_the_previous_notification_kinds_are_what_exists_after_the_migration_below(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(PREVIOUS_MIGRATION)
    after_below = set(below.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(
        below.ADDED_NOTIFICATION_KIND_VALUES
    )

    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) == after_below


def test_migration_and_models_agree_on_the_role_and_the_notification_kinds(
    load_migration: LoadMigration, assert_migration_and_model_agree: AssertMigrationAndModelAgree
) -> None:
    migration = load_migration(MIGRATION)

    assert_migration_and_model_agree(
        migration.PREVIOUS_ROLE_VALUES, migration.ADDED_ROLE_VALUES, set(Role.values())
    )
    assert_migration_and_model_agree(
        migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        migration.ADDED_NOTIFICATION_KIND_VALUES,
        {kind.value for kind in NotificationKind},
    )
    assert migration.ADDED_ROLE_VALUES == ("event_coordinator_lead",)
    assert migration.ADDED_NOTIFICATION_KIND_VALUES == ("request_queued_for_lead",)


def test_upgrade_adds_both_values_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    add_role = "ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'event_coordinator_lead'"
    add_kind = "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'request_queued_for_lead'"
    # Postgres won't let a transaction use an enum value it added, so both additions sit
    # between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index(add_role) < sql.index(add_kind) < sql.index("BEGIN")


def test_downgrade_rebuilds_both_types_without_the_new_values(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "UPDATE users SET role = 'event_coordinator' WHERE role = 'event_coordinator_lead'",
        "ALTER TYPE user_role RENAME TO user_role_old",
        "CREATE TYPE user_role AS ENUM ('event_organiser', 'attendee', 'event_coordinator', "
        "'venue_staff', 'technical_support_staff')",
        "ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::text::user_role",
        "DROP TYPE user_role_old",
        "DELETE FROM notifications WHERE kind = 'request_queued_for_lead'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted', "
        "'coordinator_assigned', 'equipment_requested', 'significant_change', "
        "'event_request_approved', 'event_request_rejected', 'clarification_requested', "
        "'clarification_answered', 'request_assigned')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
