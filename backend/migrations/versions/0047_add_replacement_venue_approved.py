"""Add the replacement_venue_approved notification kind.

Revision ID: 0047_add_replacement_approved
Revises: 0046_add_safety_review_changed
Create Date: 2026-10-26

SCRUM-92 "Flag bookings affected when a venue becomes unavailable" (ADR-0108):

* ``notification_kind`` gains ``replacement_venue_approved``, raised to the Organiser
  who submitted an event a venue sent back from Confirmed to Approved, when Venue Staff
  approve a replacement venue for it (AC9, added 26 Oct).

Revises 0046 (PR #143, SCRUM-33), which merges first; until it does, this branch has
no 0046 and can't be upgraded on its own. If another migration takes 0047's place
first, re-point ``down_revision`` and add its values to the list below. The value is
added outside the migration's transaction, with ``IF NOT EXISTS``, as 0041, 0044, 0045
and 0046 do. Downgrading deletes the rows of the new value and rebuilds the type
without it (lossy, like 0045's).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0047_add_replacement_approved"
down_revision = "0046_add_safety_review_changed"
branch_labels = None
depends_on = None

#: What migrations 0009-0046 left, in the order Postgres holds them. Downgrade rebuilds
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
)

#: Added here (SCRUM-92 AC9, ADR-0108).
ADDED_NOTIFICATION_KIND_VALUES = ("replacement_venue_approved",)


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
