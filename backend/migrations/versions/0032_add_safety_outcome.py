"""Add the safety_outcome_recorded history kind and the safety outcome notifications.

Revision ID: 0032_add_safety_outcome
Revises: 0030_add_safety_review_kind
Create Date: 2026-10-17

SCRUM-98 "Record the operational safety check outcome" (ADR-0047):

* ``event_history_entry_kind`` gains ``safety_outcome_recorded``, written when the
  Safety Officer records Approve, Reject or Request Changes (AC7).
* ``notification_kind`` gains ``safety_check_approved``, ``safety_check_rejected`` and
  ``safety_changes_requested``, raised to the assigned coordinator (AC8).

Numbered 0032 because an open pull request already adds a 0031; whichever merges last
re-points its ``down_revision``. Every value is added outside the migration's
transaction, with ``IF NOT EXISTS``, as 0029 and 0030 do. Downgrading deletes the rows
of the new values and rebuilds each type without them (lossy, like 0030's). An event
an outcome returned to planning stays ``approved``, which downgrade leaves as it is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0032_add_safety_outcome"
down_revision = "0030_add_safety_review_kind"
branch_labels = None
depends_on = None

#: What migrations 0010-0029 left. Downgrade rebuilds ``event_history_entry_kind`` with
#: just this.
PREVIOUS_HISTORY_KIND_VALUES = (
    "coordinator_assigned",
    "coordinator_reassigned",
    "field_changed",
    "event_completed",
    "review_started",
    "decision_recorded",
    "clarification_requested",
    "clarification_answered",
    "venue_booking_requested",
    "equipment_reserved",
    "venue_arrangement_changed",
    "venue_arrangement_withdrawn",
    "equipment_outcome_recorded",
    "venue_booking_approved",
    "venue_booking_rejected",
    "safety_review_requested",
)

#: Added here (SCRUM-98 AC7).
ADDED_HISTORY_KIND_VALUES = ("safety_outcome_recorded",)

#: What migrations 0009-0030 left, in the order Postgres holds them. Downgrade rebuilds
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
    "venue_booking_requested",
    "equipment_reserved",
    "request_queued_for_lead",
    "equipment_outcome_recorded",
    "venue_booking_approved",
    "venue_booking_rejected",
    "safety_review_requested",
)

#: Added here (SCRUM-98 AC8).
ADDED_NOTIFICATION_KIND_VALUES = (
    "safety_check_approved",
    "safety_check_rejected",
    "safety_changes_requested",
)


def _add_enum_values(type_name: str, values: tuple[str, ...]) -> None:
    for value in values:
        op.execute(
            sa.text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS :value").bindparams(
                value=value
            )
        )


def _rebuild_enum(type_name: str, table: str, previous_values: tuple[str, ...]) -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the table's ``kind`` column re-cast.
    op.execute(sa.text(f"ALTER TYPE {type_name} RENAME TO {type_name}_old"))
    sa.Enum(*previous_values, name=type_name).create(op.get_bind())
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN kind TYPE {type_name} USING kind::text::{type_name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {type_name}_old"))


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)
        _add_enum_values("notification_kind", ADDED_NOTIFICATION_KIND_VALUES)


def downgrade() -> None:
    # The rows holding a removed value go first; then each type is rebuilt without it.
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    _rebuild_enum("notification_kind", "notifications", PREVIOUS_NOTIFICATION_KIND_VALUES)

    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    _rebuild_enum("event_history_entry_kind", "event_history_entries", PREVIOUS_HISTORY_KIND_VALUES)
