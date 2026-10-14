"""Add the registration settings to event requests.

Revision ID: 0026_add_registration_settings
Revises: 0025_add_booking_decisions
Create Date: 2026-10-14

SCRUM-69 "Enable registration for an event and set its capacity" (ADR-0043):

* ``event_requests.registration_enabled``, whether Attendees may register (AC1). Not
  null, and false for every row that exists: nothing can have been confirmed with
  registration before this story.
* ``event_requests.registration_capacity``, how many places there are (AC2). Nullable:
  it stays empty until the assigned coordinator sets it.
* A check constraint for a capacity of at least 1, and one that an enabled event has a
  capacity, so the database keeps the rules the service enforces.

Both columns and both constraints are dropped on downgrade, so it is lossy for any
settings made since: the settings have no other home.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0026_add_registration_settings"
down_revision = "0025_add_booking_decisions"
branch_labels = None
depends_on = None

CAPACITY_CHECK = "ck_event_requests_registration_capacity_min"
ENABLED_CHECK = "ck_event_requests_enabled_registration_has_capacity"


def upgrade() -> None:
    # batch mode so SQLite can drop columns too; on PostgreSQL it's plain ALTER TABLE.
    with op.batch_alter_table("event_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "registration_enabled",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("registration_capacity", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(CAPACITY_CHECK, "registration_capacity >= 1")
        batch_op.create_check_constraint(
            ENABLED_CHECK, "NOT registration_enabled OR registration_capacity IS NOT NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("event_requests") as batch_op:
        batch_op.drop_constraint(ENABLED_CHECK, type_="check")
        batch_op.drop_constraint(CAPACITY_CHECK, type_="check")
        batch_op.drop_column("registration_capacity")
        batch_op.drop_column("registration_enabled")
