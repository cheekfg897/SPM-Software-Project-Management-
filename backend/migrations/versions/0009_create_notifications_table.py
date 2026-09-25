"""Create notifications table (notifications module).

Revision ID: 0009_create_notifications
Revises: 0008_create_equipment_types
Create Date: 2026-09-25

SCRUM-28 "Receive notifications about my events": one ``notifications`` row per
recipient, with the event's reference and name copied onto it, a
``notification_kind`` enum saying what happened, and ``read_at`` for the read state
(ADR-0015). Foreign keys to ``users`` and ``event_requests`` are database-level only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_create_notifications"
down_revision = "0008_create_equipment_types"
branch_labels = None
depends_on = None


KIND_VALUES = ("event_request_submitted",)


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("event_request_id", sa.Integer(), nullable=False),
        sa.Column("event_reference", sa.String(length=12), nullable=False),
        sa.Column("event_name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Enum(*KIND_VALUES, name="notification_kind"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notifications_recipient_id"), "notifications", ["recipient_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_recipient_id"), table_name="notifications")
    op.drop_table("notifications")
    # The PostgreSQL enum type is not dropped by drop_table; remove it
    # explicitly so a downgrade/upgrade cycle can recreate it.
    sa.Enum(name="notification_kind").drop(op.get_bind(), checkfirst=True)
