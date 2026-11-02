"""Record the coordinator's decision on a change request, and its notification kinds.

Revision ID: 0055_decide_change_requests
Revises: 0053_create_change_requests
Create Date: 2026-11-01

SCRUM-57 "Review and decide a change request" (ADR-0127):

* ``event_change_requests`` gains ``decided_at``, ``decided_by`` (a foreign key to
  ``users``, like ``requested_by``) and ``decision_reason``. A decided request must say
  when and by whom (``ck_event_change_requests_decided_has_time``), and a rejected one
  why (``ck_event_change_requests_rejected_has_reason``, AC3). The ``approved`` and
  ``rejected`` statuses already exist: 0053 created them for this story.
* ``notification_kind`` gains ``change_request_approved`` and
  ``change_request_rejected``, raised to the Organiser (AC4), and
  ``event_rescheduled``, raised to the event's registered Attendees when an approved
  change moves its date or time (AC7).

Main's head is 0053. Open pull requests #160 and #161 add 0054; whichever merges
first, this one re-points ``down_revision``, adding any notification kinds it adds to
the list below. The kinds are added outside the migration's transaction, with
``IF NOT EXISTS``, as 0049 does. Downgrading deletes the rows of the new kinds,
rebuilds ``notification_kind`` without them (lossy, like 0049's), and drops the
checks, the foreign key and the columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0055_decide_change_requests"
down_revision = "0053_create_change_requests"
branch_labels = None
depends_on = None

#: What migrations 0009-0053 left, in the order Postgres holds them. Downgrade rebuilds
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
    "change_request_raised",
    "change_request_withdrawn",
)

#: Added here (AC4, AC7).
ADDED_NOTIFICATION_KIND_VALUES = (
    "change_request_approved",
    "change_request_rejected",
    "event_rescheduled",
)

DECIDED_BY_FOREIGN_KEY = "fk_event_change_requests_decided_by"
DECIDED_HAS_TIME_CHECK = "ck_event_change_requests_decided_has_time"
REJECTED_HAS_REASON_CHECK = "ck_event_change_requests_rejected_has_reason"


def upgrade() -> None:
    op.add_column(
        "event_change_requests", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("event_change_requests", sa.Column("decided_by", sa.Integer(), nullable=True))
    op.add_column("event_change_requests", sa.Column("decision_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        DECIDED_BY_FOREIGN_KEY, "event_change_requests", "users", ["decided_by"], ["id"]
    )
    op.create_check_constraint(
        DECIDED_HAS_TIME_CHECK,
        "event_change_requests",
        "status NOT IN ('approved', 'rejected') OR "
        "(decided_at IS NOT NULL AND decided_by IS NOT NULL)",
    )
    op.create_check_constraint(
        REJECTED_HAS_REASON_CHECK,
        "event_change_requests",
        "status <> 'rejected' OR decision_reason IS NOT NULL",
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

    op.drop_constraint(REJECTED_HAS_REASON_CHECK, "event_change_requests", type_="check")
    op.drop_constraint(DECIDED_HAS_TIME_CHECK, "event_change_requests", type_="check")
    op.drop_constraint(DECIDED_BY_FOREIGN_KEY, "event_change_requests", type_="foreignkey")
    op.drop_column("event_change_requests", "decision_reason")
    op.drop_column("event_change_requests", "decided_by")
    op.drop_column("event_change_requests", "decided_at")
