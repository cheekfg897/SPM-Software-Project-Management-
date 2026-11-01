"""Add the cancelled arrangement status and its notification and history kinds.

Revision ID: 0051_add_booking_cancelled
Revises: 0050_add_needs_reassessment
Create Date: 2026-10-31

SCRUM-111 "Cancel one approved venue booking while the event is being planned"
(ADR-0117):

* ``booking_request_status`` gains ``cancelled``, for an arrangement whose approved
  booking the coordinator cancelled, which frees the venue (AC1).
* ``notification_kind`` gains ``venue_booking_cancelled``, Venue Staff's notice (AC3),
  and ``safety_review_venue_cancelled``, the Safety Officers' (AC2).
* ``event_history_entry_kind`` gains ``venue_booking_cancelled``, the entry that keeps
  the cancellation and its reason (AC5).

Revises 0050 (SCRUM-60), which this branch is stacked on, after 0049 (SCRUM-59). If
another migration lands first, re-point ``down_revision`` at the head it leaves and add
any values it gave these types to the lists below. Each value is added outside the
migration's transaction, with ``IF NOT EXISTS``, as 0039 and 0049 do. Downgrading
deletes the rows of the new kinds, turns a cancelled arrangement into a released one
(neither holds its venue), and rebuilds each type without the new values.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0051_add_booking_cancelled"
down_revision = "0050_add_needs_reassessment"
branch_labels = None
depends_on = None

#: What migrations 0020-0039 left, in the order Postgres holds them. Downgrade rebuilds
#: ``booking_request_status`` with just this.
PREVIOUS_REQUEST_STATUS_VALUES = (
    "pending",
    "withdrawn",
    "approved",
    "rejected",
    "conflicting",
    "on_hold",
    "expired",
    "released",
)
#: Added here (AC1).
ADDED_REQUEST_STATUS_VALUES = ("cancelled",)

#: What migrations 0009-0049 left, in the order Postgres holds them. Downgrade rebuilds
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
)
#: Added here: Venue Staff's notice (AC3) and the Safety Officers' (AC2).
ADDED_NOTIFICATION_KIND_VALUES = ("venue_booking_cancelled", "safety_review_venue_cancelled")

#: What migrations 0010-0049 left, in the order Postgres holds them. Downgrade rebuilds
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
)
#: Added here (AC5).
ADDED_HISTORY_KIND_VALUES = ("venue_booking_cancelled",)

#: The pending index 0036 left, which the request status rebuild has to drop and put
#: back: its predicate can't be re-created against the renamed type (as in 0039).
PENDING_INDEX = "uq_venue_booking_requests_pending"
PENDING_CONFLICTING_OR_ON_HOLD = "status IN ('pending', 'conflicting', 'on_hold')"


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
        _add_enum_values("booking_request_status", ADDED_REQUEST_STATUS_VALUES)
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

    # A cancelled arrangement no longer holds its venue, as a released one doesn't, and
    # neither is Pending, Conflicting or On Hold, so the change can't break the pending
    # index.
    op.drop_index(PENDING_INDEX, table_name="venue_booking_requests")
    op.execute(
        sa.text("UPDATE venue_booking_requests SET status = 'released' WHERE status = 'cancelled'")
    )
    _rebuild_enum(
        "booking_request_status", "venue_booking_requests", "status", PREVIOUS_REQUEST_STATUS_VALUES
    )
    op.create_index(
        PENDING_INDEX,
        "venue_booking_requests",
        ["event_id", "venue_id", "starts_at", "ends_at"],
        unique=True,
        postgresql_where=sa.text(PENDING_CONFLICTING_OR_ON_HOLD),
    )
