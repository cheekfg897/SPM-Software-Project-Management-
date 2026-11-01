"""Add the notification and history kinds for a cancelled event.

Revision ID: 0052_add_event_cancelled
Revises: 0051_add_booking_cancelled
Create Date: 2026-10-31

SCRUM-61 "Cancel an event and release its arrangements" (ADR-0122):

* ``notification_kind`` gains ``event_cancelled``, the notice the event's assigned
  coordinator (AC1) and every registered Attendee (AC4) get, and
  ``venue_booking_released_by_cancellation``, Venue Staff's notice of each booking or
  hold the cancellation released (AC8).
* ``event_history_entry_kind`` gains ``event_cancelled``, the entry that keeps who
  cancelled the event and why (AC1).

``event_request_status`` already holds ``cancelled`` (migration 0008), so it is
untouched.

It revises 0051 (SCRUM-111), the head of the branch it is stacked on. Other open pull
requests also add migrations: ``0051_add_suggested_alternative`` (SCRUM-70), which also
revises 0050, ``0050_add_registration_notification_kinds`` (SCRUM-62) and
``0053_create_change_requests`` (SCRUM-56). Whichever lands later is renumbered: it
re-points ``down_revision`` at the head the other leaves and adds the other's values to
the previous lists below, so the downgrade rebuilds each type with everything below it.
Each value is added outside the migration's transaction, with ``IF NOT EXISTS``, as 0049
and 0051 do. Downgrading deletes the rows of the new kinds, then rebuilds each type
without them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0052_add_event_cancelled"
down_revision = "0051_add_booking_cancelled"
branch_labels = None
depends_on = None

#: What migrations 0009-0051 left, in the order Postgres holds them. Downgrade rebuilds
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
    "event_confirmed",
    "venue_hold_placed",
    "venue_hold_expiry_changed",
    "venue_hold_expiring",
    "venue_hold_expired",
    "alternative_venue_needed",
    "venue_booking_conflicting",
    "venue_available_again",
    "venue_booking_released",
    "safety_review_event_changed",
    "replacement_venue_approved",
    "venue_booking_reconfirmed",
    "venue_booking_cancelled",
    "safety_review_venue_cancelled",
)
#: Added here: the coordinator's and Attendees' notice (AC1, AC4), and Venue Staff's
#: (AC8).
ADDED_NOTIFICATION_KIND_VALUES = ("event_cancelled", "venue_booking_released_by_cancellation")

#: What migrations 0010-0051 left, in the order Postgres holds them. Downgrade rebuilds
#: ``event_history_entry_kind`` with just this.
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
    "event_confirmed",
    "venue_preparation_updated",
    "equipment_preparation_updated",
    "venue_hold_expired",
    "alternative_venue_needed",
    "safety_approval_withdrawn",
    "venue_booking_reconfirmed",
    "venue_booking_cancelled",
)
#: Added here (AC1).
ADDED_HISTORY_KIND_VALUES = ("event_cancelled",)


def _add_enum_values(type_name: str, values: tuple[str, ...]) -> None:
    for value in values:
        op.execute(
            sa.text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS :value").bindparams(
                value=value
            )
        )


def _rebuild_enum(
    type_name: str, table: str, column: str, previous_values: tuple[str, ...]
) -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the table's column re-cast.
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
        _add_enum_values("notification_kind", ADDED_NOTIFICATION_KIND_VALUES)
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)


def downgrade() -> None:
    # The rows holding a removed kind go first; then each type is rebuilt without it.
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    _rebuild_enum("notification_kind", "notifications", "kind", PREVIOUS_NOTIFICATION_KIND_VALUES)
    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    _rebuild_enum(
        "event_history_entry_kind", "event_history_entries", "kind", PREVIOUS_HISTORY_KIND_VALUES
    )
