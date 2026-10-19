"""Add the flags a significant change leaves on a venue arrangement.

Revision ID: 0043_add_reassessment_flags
Revises: 0042_add_withdrawal_cut_off
Create Date: 2026-10-19

SCRUM-33 AC6 "only the arrangements the change affects are flagged" (ADR-0094):

* ``reassessment_flag_kind`` is a new type: ``requires_reconfirmation`` or
  ``no_longer_suitable``, SCRUM-58's two words for a booking a change unsettled.
* ``reassessment_flags`` holds one row for each reason a change gave to flag an
  arrangement, with the kind and the reason Venue Staff are told.

Revises 0042, main's head when this was rebased; whichever open migration merges
later re-points its ``down_revision``. Downgrading drops the table and then the type,
which ``drop_table`` leaves behind.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0043_add_reassessment_flags"
down_revision = "0042_add_withdrawal_cut_off"
branch_labels = None
depends_on = None

#: The new type's values.
FLAG_KIND_VALUES = ("requires_reconfirmation", "no_longer_suitable")
FLAG_KIND_TYPE = "reassessment_flag_kind"


def upgrade() -> None:
    op.create_table(
        "reassessment_flags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("booking_request_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Enum(*FLAG_KIND_VALUES, name=FLAG_KIND_TYPE), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["booking_request_id"], ["venue_booking_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reassessment_flags_booking_request_id"),
        "reassessment_flags",
        ["booking_request_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reassessment_flags_booking_request_id"), table_name="reassessment_flags")
    op.drop_table("reassessment_flags")
    sa.Enum(name=FLAG_KIND_TYPE).drop(op.get_bind(), checkfirst=True)
