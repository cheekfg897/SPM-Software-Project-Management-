"""Add the request_assigned notification kind.

Revision ID: 0019_add_review_kinds
Revises: 0018_add_clarification
Create Date: 2026-09-26

SCRUM-39 "Be notified about review and approval decisions" (ADR-0030):

* ``notification_kind`` gains ``request_assigned``, raised to the organiser who
  submitted a request when an Event Coordinator is assigned to it (AC1).

AC2's clarification notifications come from SCRUM-32's migration (ADR-0029), not
this one.

The enum value is added outside the migration's transaction, with ``IF NOT EXISTS``,
as 0010, 0012 and 0015 do. Downgrading deletes the rows of the new kind and rebuilds
the enum type without it (lossy, like 0015's).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0019_add_review_kinds"
down_revision = "0018_add_clarification"
branch_labels = None
depends_on = None

#: What migrations 0009, 0010, 0011, 0015, 0017 and 0018 created. Downgrade rebuilds
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
)

#: Added here (SCRUM-39 AC1).
ADDED_NOTIFICATION_KIND_VALUES = ("request_assigned",)


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
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the column re-cast; rows of the removed kind go first.
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    op.execute(sa.text("ALTER TYPE notification_kind RENAME TO notification_kind_old"))
    sa.Enum(*PREVIOUS_NOTIFICATION_KIND_VALUES, name="notification_kind").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE notifications ALTER COLUMN kind "
            "TYPE notification_kind USING kind::text::notification_kind"
        )
    )
    op.execute(sa.text("DROP TYPE notification_kind_old"))
