"""Add withdrawn registrations.

Revision ID: 0031_add_withdrawn_registrations
Revises: 0034_add_equipment_preparation
Create Date: 2026-10-16

SCRUM-53 "See and withdraw my registration" (ADR-0032):

* ``registration_status`` gains ``withdrawn``. A withdrawal keeps the row, so the
  unique (event, attendee) pair stays and registering again sets the same row back.
* ``registrations.withdrawn_at``, when the Attendee withdrew. Nullable: it is empty
  while they hold the place.

Numbered 0031 but chained after 0034, main's head when it was rebased (0035 → 0038 →
0033 → 0034 merged first); whichever open migration merges after this one re-points
its ``down_revision``. No migration between 0027 and 0034 touches
``registration_status``. The value is added outside the
migration's transaction, with ``IF NOT EXISTS``, as 0023 does. Downgrading is lossy:
withdrawn registrations are deleted, since ``withdrawn`` has no earlier representation,
and the type is rebuilt without it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0031_add_withdrawn_registrations"
down_revision = "0034_add_equipment_preparation"
branch_labels = None
depends_on = None

#: What migration 0027 created. Downgrade rebuilds ``registration_status`` with this.
PREVIOUS_STATUS_VALUES = ("registered",)

#: Added here (SCRUM-53).
ADDED_STATUS_VALUES = ("withdrawn",)


def upgrade() -> None:
    op.add_column(
        "registrations", sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Postgres won't let a transaction use an enum value it added itself, so the
    # addition runs outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_STATUS_VALUES:
            op.execute(
                sa.text("ALTER TYPE registration_status ADD VALUE IF NOT EXISTS :value").bindparams(
                    value=value
                )
            )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM registrations WHERE status = 'withdrawn'"))
    op.drop_column("registrations", "withdrawn_at")
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the column re-cast.
    op.execute(sa.text("ALTER TYPE registration_status RENAME TO registration_status_old"))
    sa.Enum(*PREVIOUS_STATUS_VALUES, name="registration_status").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE registrations ALTER COLUMN status "
            "TYPE registration_status USING status::text::registration_status"
        )
    )
    op.execute(sa.text("DROP TYPE registration_status_old"))
