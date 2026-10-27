"""Mark an equipment reservation for reassessment.

Revision ID: 0050_add_needs_reassessment
Revises: 0049_add_booking_reconfirmed
Create Date: 2026-10-28

SCRUM-60 "Reassess equipment reservations after a timing change" (ADR-0114):

* ``equipment_reservations.needs_reassessment``: set when the event's date or time, or
  its line's quantity, changes after the units were reserved (AC1, AC8), and cleared
  when Technical Support confirm the reservation for the event's period or record the
  line's outcome (AC3, AC4). It defaults to false, so existing reservations are
  unmarked.

No enum gains a value: confirming a reservation tells the coordinator with an existing
notification kind. Revises 0049 (SCRUM-59), which this branch is stacked on, after
0048 (PR #149, SCRUM-89). If another migration lands first, re-point ``down_revision``
at the head it leaves. Downgrading drops
the column, which loses which reservations were awaiting reassessment.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0050_add_needs_reassessment"
down_revision = "0049_add_booking_reconfirmed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "equipment_reservations",
        sa.Column("needs_reassessment", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("equipment_reservations", "needs_reassessment")
