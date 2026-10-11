"""Add the Event Coordinator Lead role and its queue notification kind.

Revision ID: 0022_add_lead_role
Revises: 0019_add_review_kinds
Create Date: 2026-10-10

SCRUM-95 "Newly submitted event requests come to the Event Coordinator Lead unassigned"
(ADR-0036):

* ``user_role`` gains ``event_coordinator_lead``, the internal role that assigns each
  submitted request to a coordinator (AC7).
* ``notification_kind`` gains ``request_queued_for_lead``, raised to the Lead when a
  request enters the unassigned queue (AC4).

Both values are added outside the migration's transaction, with ``IF NOT EXISTS``, as
0019 does. Downgrading rebuilds both enum types without the new values (lossy): a Lead
account goes back to ``event_coordinator`` and the notifications of the new kind are
deleted.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0022_add_lead_role"
down_revision = "0021_add_equipment_reservations"
branch_labels = None
depends_on = None

#: What migration 0001 created. Downgrade rebuilds ``user_role`` with just this.
PREVIOUS_ROLE_VALUES = (
    "event_organiser",
    "attendee",
    "event_coordinator",
    "venue_staff",
    "technical_support_staff",
)

#: Added here (SCRUM-95 AC7).
ADDED_ROLE_VALUES = ("event_coordinator_lead",)

#: What migrations 0009, 0010, 0011, 0015, 0017, 0018 and 0019 left. Downgrade rebuilds
#: ``notification_kind`` with just this.
PREVIOUS_NOTIFICATION_KIND_VALUES = (
    "event_request_submitted",
    "coordinator_assigned",
    "equipment_requested",
    "significant_change",
    "event_request_approved",
    "event_request_rejected",
    "clarification_requested",
    "clarification_answered",
    "request_assigned",
    # Added below us in the stack: 0020 (SCRUM-42) and 0021 (SCRUM-46).
    "venue_booking_requested",
    "equipment_reserved",
)

#: Added here (SCRUM-95 AC4).
ADDED_NOTIFICATION_KIND_VALUES = ("request_queued_for_lead",)


def _add_enum_values(type_name: str, values: tuple[str, ...]) -> None:
    for value in values:
        op.execute(
            sa.text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS :value").bindparams(
                value=value
            )
        )


def _rebuild_enum_without_added_values(
    type_name: str, table: str, column: str, previous_values: tuple[str, ...]
) -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the column re-cast.
    op.execute(sa.text(f"ALTER TYPE {type_name} RENAME TO {type_name}_old"))
    sa.Enum(*previous_values, name=type_name).create(op.get_bind())
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE {type_name} USING {column}::text::{type_name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {type_name}_old"))


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("user_role", ADDED_ROLE_VALUES)
        _add_enum_values("notification_kind", ADDED_NOTIFICATION_KIND_VALUES)


def downgrade() -> None:
    # A Lead account goes back to the role it was promoted from, and a notification of
    # the removed kind is deleted, before each type is rebuilt.
    op.execute(
        sa.text("UPDATE users SET role = 'event_coordinator' WHERE role = 'event_coordinator_lead'")
    )
    _rebuild_enum_without_added_values("user_role", "users", "role", PREVIOUS_ROLE_VALUES)
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    _rebuild_enum_without_added_values(
        "notification_kind", "notifications", "kind", PREVIOUS_NOTIFICATION_KIND_VALUES
    )
