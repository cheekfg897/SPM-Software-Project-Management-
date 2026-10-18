"""Add the venue_booking_conflicting notification kind.

Revision ID: 0041_add_booking_conflicting
Revises: 0039_flag_alternative_venues
Create Date: 2026-10-18

SCRUM-50 "Be notified about booking and equipment decisions" (ADR-0055):

* ``notification_kind`` gains ``venue_booking_conflicting``, raised to every Venue Staff
  user when a change to a venue's setup or turnaround time marks a confirmed booking
  Conflicting (AC6).

Revises 0039, main's head when it was rebased; whichever open migration merges later
re-points its ``down_revision``. The value is added outside
the migration's transaction, with ``IF NOT EXISTS``, as 0035 does. Downgrading deletes
the rows of the new value and rebuilds the type without it (lossy, like 0035's). The
revision id is shorter than the file name, because the full name exceeds the
``alembic_version`` column's 32 characters, as 0024's does.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0041_add_booking_conflicting"
down_revision = "0039_flag_alternative_venues"
branch_labels = None
depends_on = None

#: What migrations 0009-0039 left, in the order Postgres holds them. Downgrade rebuilds
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
)

#: Added here (SCRUM-50 AC6).
ADDED_NOTIFICATION_KIND_VALUES = ("venue_booking_conflicting",)


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
