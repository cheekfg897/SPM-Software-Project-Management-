"""Record who returned units to service and flag reservations that are left short.

Revision ID: 0038_add_out_of_service_audit
Revises: 0035_add_event_confirmed
Create Date: 2026-10-16

SCRUM-47 "Take damaged equipment out of circulation" (ADR-0046):

* ``equipment_out_of_service.resolved_by``: who put the units back (AC4). Nullable, as
  ``resolved_at`` is, while the units are still out. A database-level foreign key to
  ``users`` only.
* ``equipment_reservations.needs_attention``: set while units out of service leave the
  type short of what is reserved for that reservation's period (AC3). It defaults to
  false, so existing reservations are unflagged.

No enum gains a value: the coordinator is told with an existing notification kind.
Downgrading drops both columns, which loses who returned units and which reservations
were flagged.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0038_add_out_of_service_audit"
down_revision = "0035_add_event_confirmed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "equipment_out_of_service",
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "equipment_reservations",
        sa.Column("needs_attention", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("equipment_reservations", "needs_attention")
    op.drop_column("equipment_out_of_service", "resolved_by")
