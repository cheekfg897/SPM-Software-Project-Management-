"""Add the venue_booking_released notification kind.

Revision ID: 0045_add_venue_booking_released
Revises: 0044_add_venue_available_again
Create Date: 2026-10-25

SCRUM-49 "Confirm an event once its arrangements are in place" (ADR-0103):

* ``notification_kind`` gains ``venue_booking_released``, raised to every Venue Staff
  user when rejecting an event during planning releases one of its approved bookings
  or holds (AC10, the Product Owner's answer of 25 Oct).

Revises 0044 (SCRUM-92's branch, which this one is stacked on); whichever open
migration merges later re-points its ``down_revision``. The value is added outside the
migration's transaction, with ``IF NOT EXISTS``, as 0041 and 0044 do. Downgrading
deletes the rows of the new value and rebuilds the type without it (lossy, like
0044's).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0045_add_venue_booking_released"
down_revision = "0044_add_venue_available_again"
branch_labels = None
depends_on = None

#: What migrations 0009-0044 left, in the order Postgres holds them. Downgrade rebuilds
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
)

#: Added here (SCRUM-49 AC10, ADR-0103).
ADDED_NOTIFICATION_KIND_VALUES = ("venue_booking_released",)


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # addition runs outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_NOTIFICATION_KIND_VALUES:
            op.execute(
                sa.text("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS :value").bindparams(
                    value=value
                )
            )


def downgrade() -> None:
    # The rows holding a removed value go first. Postgres can't remove an enum value,
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
