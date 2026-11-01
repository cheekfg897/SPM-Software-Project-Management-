"""Create the event_change_requests table and its notification kinds.

Revision ID: 0053_create_change_requests
Revises: 0050_add_needs_reassessment
Create Date: 2026-11-01

SCRUM-56 "Request a change after submitting my event" (ADR-0126):

* ``event_change_requests`` holds an Organiser's change request: what should change
  (``requested_values``), the value each of those fields had when it was raised
  (``previous_values``, for SCRUM-57's stale check), why, who raised it and when, and
  its status in the new ``event_change_request_status`` enum. ``approved`` and
  ``rejected`` are SCRUM-57's, created now so it needs no enum change.
* ``uq_event_change_requests_pending``, a partial unique index on ``event_request_id``
  where ``status = 'pending'``, keeps one Pending request per event (AC7).
* ``notification_kind`` gains ``change_request_raised`` and
  ``change_request_withdrawn``, raised to the event's assigned coordinator (AC5, AC8).

Revises 0050 (SCRUM-60), main's head when it was written, which changes no enum; 0049
is the last to change ``notification_kind``. Open pull requests also add 0051 and
0052; whichever merges first, this one is renumbered and re-points ``down_revision``,
adding any notification kinds they add to the list below. The kinds are added outside
the migration's transaction, with ``IF NOT EXISTS``, as 0049 does. Downgrading deletes
the rows of the new kinds, rebuilds ``notification_kind`` without them (lossy, like
0049's), and drops the indexes, the table and its enum type.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0053_create_change_requests"
down_revision = "0050_add_needs_reassessment"
branch_labels = None
depends_on = None

#: The values of the new ``event_change_request_status`` type, in the model's order.
CHANGE_REQUEST_STATUS_VALUES = ("pending", "approved", "rejected", "withdrawn")

#: What migrations 0009-0050 left, in the order Postgres holds them. Downgrade rebuilds
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

#: Added here (AC5, AC8).
ADDED_NOTIFICATION_KIND_VALUES = ("change_request_raised", "change_request_withdrawn")


def upgrade() -> None:
    op.create_table(
        "event_change_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_request_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("requested_values", sa.JSON(), nullable=False),
        sa.Column("previous_values", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*CHANGE_REQUEST_STATUS_VALUES, name="event_change_request_status"),
            nullable=False,
        ),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawal_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status <> 'withdrawn' OR withdrawn_at IS NOT NULL",
            name="ck_event_change_requests_withdrawn_has_time",
        ),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_event_change_requests_event_request_id"),
        "event_change_requests",
        ["event_request_id"],
        unique=False,
    )
    op.create_index(
        "uq_event_change_requests_pending",
        "event_change_requests",
        ["event_request_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_NOTIFICATION_KIND_VALUES:
            op.execute(
                sa.text("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS :value").bindparams(
                    value=value
                )
            )


def downgrade() -> None:
    # The rows holding a removed kind go first. Postgres can't remove an enum value,
    # so the type is then rebuilt with its previous list and the column re-cast.
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    op.execute(sa.text("ALTER TYPE notification_kind RENAME TO notification_kind_old"))
    sa.Enum(*PREVIOUS_NOTIFICATION_KIND_VALUES, name="notification_kind").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE notifications ALTER COLUMN kind"
            " TYPE notification_kind USING kind::text::notification_kind"
        )
    )
    op.execute(sa.text("DROP TYPE notification_kind_old"))

    op.drop_index(
        "uq_event_change_requests_pending",
        table_name="event_change_requests",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(
        op.f("ix_event_change_requests_event_request_id"), table_name="event_change_requests"
    )
    op.drop_table("event_change_requests")
    # drop_table leaves the enum type behind.
    sa.Enum(name="event_change_request_status").drop(op.get_bind(), checkfirst=True)
