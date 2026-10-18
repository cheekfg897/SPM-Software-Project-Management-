"""Add tentative holds: the on-hold request status and a hold's expiry.

Revision ID: 0036_add_tentative_holds
Revises: 0031_add_withdrawn_registrations
Create Date: 2026-10-17

SCRUM-75 "Place a tentative hold on a venue" (ADR-0045):

* ``bookings`` gains ``hold_expires_at``, when a tentative hold stops holding the venue.
* ``venue_booking_requests`` gains ``booking_id``, the booking that holds the venue for
  a request that is On Hold.
* ``booking_request_status`` gains ``on_hold``, and the pending index counts it: a
  request On Hold still blocks a second one for its event, venue and period
  (SCRUM-42 AC7).
* ``notification_kind`` gains ``venue_hold_placed`` and ``venue_hold_expiry_changed``,
  the notices the coordinator gets when a hold is placed and when its expiry changes.

The values are added outside the migration's transaction, with ``IF NOT EXISTS``, as
0025 and 0028 do. Postgres can't remove an enum value, so downgrading rebuilds both
types without the new values. It is lossy for holds, for the reason 0025 gives for
decisions: a request On Hold is deleted rather than returned to ``pending``, because
the old schema cannot say the venue is held and a resurrected Pending request would ask
Venue Staff to decide a venue that is already held; and the tentative bookings the holds
made are deleted with them, because without an expiry nothing would ever release them.
A hold that was confirmed keeps its booking, which is an ordinary one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0036_add_tentative_holds"
down_revision = "0031_add_withdrawn_registrations"
branch_labels = None
depends_on = None

#: What migrations 0020, 0023, 0025 and 0028 left. Downgrade rebuilds
#: ``booking_request_status`` with just this.
PREVIOUS_REQUEST_STATUS_VALUES = ("pending", "withdrawn", "approved", "rejected", "conflicting")

#: Added here (SCRUM-75 AC1).
ADDED_REQUEST_STATUS_VALUES = ("on_hold",)

#: The statuses the pending index covers after this migration (SCRUM-42 AC7).
PENDING_CONFLICTING_OR_ON_HOLD = "status IN ('pending', 'conflicting', 'on_hold')"

#: What migrations 0009-0035 left. Downgrade rebuilds ``notification_kind`` with just
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
)

#: Added here (SCRUM-75 AC9): the coordinator is told when a hold is placed and when
#: its expiry changes.
ADDED_NOTIFICATION_KIND_VALUES = ("venue_hold_placed", "venue_hold_expiry_changed")


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
    op.add_column("bookings", sa.Column("hold_expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "venue_booking_requests",
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id")),
    )
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("booking_request_status", ADDED_REQUEST_STATUS_VALUES)
        _add_enum_values("notification_kind", ADDED_NOTIFICATION_KIND_VALUES)
    # The new value is committed by now, so the index can name it, as 0028 does.
    op.drop_index("uq_venue_booking_requests_pending", table_name="venue_booking_requests")
    op.create_index(
        "uq_venue_booking_requests_pending",
        "venue_booking_requests",
        ["event_id", "venue_id", "starts_at", "ends_at"],
        unique=True,
        postgresql_where=sa.text(PENDING_CONFLICTING_OR_ON_HOLD),
    )


def downgrade() -> None:
    # The requests go first: they point at the bookings.
    op.execute(sa.text("DELETE FROM venue_booking_requests WHERE status = 'on_hold'"))
    op.execute(
        sa.text("DELETE FROM bookings WHERE status = 'tentative' AND hold_expires_at IS NOT NULL")
    )
    op.drop_column("venue_booking_requests", "booking_id")
    op.drop_column("bookings", "hold_expires_at")
    # The pending index's predicate (status = 'pending') can't be re-created against
    # the renamed enum type, so it is dropped around the rebuild, as 0028 does.
    op.drop_index("uq_venue_booking_requests_pending", table_name="venue_booking_requests")
    _rebuild_enum_without_added_values(
        "booking_request_status",
        "venue_booking_requests",
        "status",
        PREVIOUS_REQUEST_STATUS_VALUES,
    )
    op.create_index(
        "uq_venue_booking_requests_pending",
        "venue_booking_requests",
        ["event_id", "venue_id", "starts_at", "ends_at"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    _rebuild_enum_without_added_values(
        "notification_kind",
        "notifications",
        "kind",
        PREVIOUS_NOTIFICATION_KIND_VALUES,
    )
