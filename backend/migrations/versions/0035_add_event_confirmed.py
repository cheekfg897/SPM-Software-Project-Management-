"""Add the event_confirmed history kind and notification kind.

Revision ID: 0035_add_event_confirmed
Revises: 0032_add_safety_outcome
Create Date: 2026-10-17

SCRUM-49 "Confirm an event once its arrangements are in place" (ADR-0051):

* ``event_history_entry_kind`` gains ``event_confirmed``, written when the assigned
  coordinator confirms the event.
* ``notification_kind`` gains ``event_confirmed``, raised to the event's organiser
  (AC12).

Numbered 0035 and revising 0032 because open pull requests already add 0033 and 0034;
whichever merges last re-points its ``down_revision``. Each value is added outside the
migration's transaction, with ``IF NOT EXISTS``, as 0029, 0030 and 0032 do. Downgrading
deletes the rows of the new value and rebuilds each type without it (lossy, like
0032's). An event that was confirmed stays ``confirmed``, which downgrade leaves as it
is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0035_add_event_confirmed"
down_revision = "0032_add_safety_outcome"
branch_labels = None
depends_on = None

#: What migrations 0010-0032 left. Downgrade rebuilds ``event_history_entry_kind`` with
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
    "safety_outcome_recorded",
)

#: Added here (SCRUM-49 AC1).
ADDED_HISTORY_KIND_VALUES = ("event_confirmed",)

#: What migrations 0009-0032 left, in the order Postgres holds them. Downgrade rebuilds
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
    "safety_check_approved",
    "safety_check_rejected",
    "safety_changes_requested",
)

#: Added here (SCRUM-49 AC12).
ADDED_NOTIFICATION_KIND_VALUES = ("event_confirmed",)


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
