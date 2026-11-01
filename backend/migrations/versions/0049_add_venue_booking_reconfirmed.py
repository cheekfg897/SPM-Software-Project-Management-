"""Add the venue_booking_reconfirmed notification and history kinds.

Revision ID: 0049_add_booking_reconfirmed
Revises: 0048_create_revoked_tokens
Create Date: 2026-10-28

SCRUM-59 "Reconfirm or reject a booking flagged after a change" (ADR-0112):

* ``notification_kind`` gains ``venue_booking_reconfirmed``, raised to the event's
  assigned coordinator when Venue Staff reconfirm a flagged arrangement (AC2, AC11).
* ``event_history_entry_kind`` gains ``venue_booking_reconfirmed``, the entry that
  records it, with the period and occupancy before and after (AC2, AC10).

Revises 0048 (PR #149, SCRUM-89), the newest migration on main when this one was added.
If another migration takes 0049's place first, re-point ``down_revision`` and add its
values to the lists below. Each value is added outside the migration's transaction,
with ``IF NOT EXISTS``, as 0039 and 0047 do. Downgrading deletes the rows of the new
values and rebuilds each type without them (lossy, like 0047's).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0049_add_booking_reconfirmed"
down_revision = "0048_create_revoked_tokens"
branch_labels = None
depends_on = None

#: What migrations 0009-0047 left, in the order Postgres holds them. Downgrade rebuilds
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
)

#: Added here (AC2).
ADDED_NOTIFICATION_KIND_VALUES = ("venue_booking_reconfirmed",)

#: What migrations 0010-0039 left, in the order Postgres holds them. Downgrade rebuilds
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
)

#: Added here (AC2).
ADDED_HISTORY_KIND_VALUES = ("venue_booking_reconfirmed",)


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
    # The rows holding a removed value go first; then each type is rebuilt without it.
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
