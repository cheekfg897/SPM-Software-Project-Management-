"""Create event_requests table (events module).

Revision ID: 0002_create_event_requests
Revises: 0001_create_users
Create Date: 2026-09-15

SCRUM-19 "Submit an event request": the ``event_requests`` table with a unique
reference (ADR-0004), a foreign key to the requesting organiser, the optional
overnight ``end_date`` (ADR-0002) and the ``event_request_status`` enum.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_create_event_requests"
down_revision = "0001_create_users"
branch_labels = None
depends_on = None


STATUS_VALUES = ("submitted",)


def upgrade() -> None:
    op.create_table(
        "event_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reference", sa.String(length=12), nullable=False),
        sa.Column("organiser_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("proposed_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("expected_attendance", sa.Integer(), nullable=False),
        sa.Column("venue_requirements", sa.Text(), nullable=True),
        sa.Column("accessibility_needs", sa.Text(), nullable=True),
        sa.Column("equipment_requirements", sa.Text(), nullable=True),
        sa.Column(
            "registration_required",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("status", sa.Enum(*STATUS_VALUES, name="event_request_status"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expected_attendance >= 1", name="ck_event_requests_expected_attendance_min"
        ),
        sa.ForeignKeyConstraint(["organiser_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference", name="uq_event_requests_reference"),
    )
    op.create_index(
        op.f("ix_event_requests_organiser_id"), "event_requests", ["organiser_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_event_requests_organiser_id"), table_name="event_requests")
    op.drop_table("event_requests")
    # The PostgreSQL enum type is not dropped by drop_table; remove it
    # explicitly. checkfirst makes this a no-op on databases without CREATE TYPE.
    sa.Enum(name="event_request_status").drop(op.get_bind(), checkfirst=True)
