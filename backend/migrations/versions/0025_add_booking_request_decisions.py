"""Add the approved and rejected request statuses and the decision reason.

Revision ID: 0025_add_booking_decisions
Revises: 0024_add_equipment_outcome
Create Date: 2026-10-14

SCRUM-43 "Approve, hold or reject a venue booking" (ADR-0042):

* ``venue_booking_requests`` gains ``decision_reason``, why Venue Staff decided as they
  did; a rejection must have one (AC6).
* ``booking_request_status`` gains ``approved`` and ``rejected`` (AC3).
* ``event_history_entry_kind`` and ``notification_kind`` gain
  ``venue_booking_approved`` and ``venue_booking_rejected`` (AC3, AC6).

``on_hold`` is deliberately **not** added: nothing can place a hold until SCRUM-75, and
Postgres keeps every value a type has ever had, so values arrive with the code that
produces them (ADR-0035 decision 3).

Values are added outside the migration's transaction, with ``IF NOT EXISTS``, as 0019,
0022, 0023 and 0024 do. Downgrading rebuilds the three enum types without the new
values and is lossy in two ways, both for the reason 0023 gives: a decided request is
deleted rather than returned to ``pending``, because the old schema cannot say a
request was decided and a resurrected Pending request would ask Venue Staff to decide a
venue that is already booked; and the confirmed booking an approval made stays, because
nothing on the booking says which request made it, and in the old schema it is an
ordinary booking.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0025_add_booking_decisions"
down_revision = "0024_add_equipment_outcome"
branch_labels = None
depends_on = None

#: What migrations 0020 and 0023 left. Downgrade rebuilds ``booking_request_status``
#: with just this.
PREVIOUS_REQUEST_STATUS_VALUES = ("pending", "withdrawn")

#: Added here (SCRUM-43 AC3).
ADDED_REQUEST_STATUS_VALUES = ("approved", "rejected")

#: What migrations 0009-0024 left. Downgrade rebuilds ``event_history_entry_kind``
#: with just this.
PREVIOUS_HISTORY_KIND_VALUES = (
    "coordinator_assigned",
    "coordinator_reassigned",
    "field_changed",
    "event_completed",
    "review_started",
    "decision_recorded",
    "clarification_requested",
    "clarification_answered",
    # Added below us in the stack: 0020 (SCRUM-42), 0021 (SCRUM-46), 0023 (SCRUM-93)
    # and 0024 (SCRUM-48).
    "venue_booking_requested",
    "equipment_reserved",
    "venue_arrangement_changed",
    "venue_arrangement_withdrawn",
    "equipment_outcome_recorded",
)

#: Added here (SCRUM-43 AC3): the audit entries for deciding a request.
ADDED_HISTORY_KIND_VALUES = ("venue_booking_approved", "venue_booking_rejected")

#: What migrations 0009-0024 left. Downgrade rebuilds ``notification_kind`` with just
#: this.
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
    # Added below us in the stack: 0020 (SCRUM-42), 0021 (SCRUM-46), 0022 (SCRUM-95)
    # and 0024 (SCRUM-48).
    "venue_booking_requested",
    "equipment_reserved",
    "request_queued_for_lead",
    "equipment_outcome_recorded",
)

#: Added here (SCRUM-43 AC6): the coordinator is told either way.
ADDED_NOTIFICATION_KIND_VALUES = ("venue_booking_approved", "venue_booking_rejected")


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


def _drop_pending_index() -> None:
    op.drop_index("uq_venue_booking_requests_pending", table_name="venue_booking_requests")


def _create_pending_index() -> None:
    # Same definition as migrations 0020 and 0023 (SCRUM-42 AC6).
    op.create_index(
        "uq_venue_booking_requests_pending",
        "venue_booking_requests",
        ["event_id", "venue_id", "starts_at", "ends_at"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def upgrade() -> None:
    op.add_column("venue_booking_requests", sa.Column("decision_reason", sa.Text()))
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("booking_request_status", ADDED_REQUEST_STATUS_VALUES)
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)
        _add_enum_values("notification_kind", ADDED_NOTIFICATION_KIND_VALUES)


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM venue_booking_requests WHERE status IN ('approved', 'rejected')")
    )
    op.drop_column("venue_booking_requests", "decision_reason")
    # The pending index's predicate (status = 'pending') can't be re-created against
    # the renamed enum type, so it is dropped around the rebuild, as 0023 does.
    _drop_pending_index()
    _rebuild_enum_without_added_values(
        "booking_request_status",
        "venue_booking_requests",
        "status",
        PREVIOUS_REQUEST_STATUS_VALUES,
    )
    _create_pending_index()
    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    _rebuild_enum_without_added_values(
        "event_history_entry_kind",
        "event_history_entries",
        "kind",
        PREVIOUS_HISTORY_KIND_VALUES,
    )
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    _rebuild_enum_without_added_values(
        "notification_kind",
        "notifications",
        "kind",
        PREVIOUS_NOTIFICATION_KIND_VALUES,
    )
