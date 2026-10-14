"""Create the registrations table (registration module).

Revision ID: 0027_create_registrations
Revises: 0026_add_registration_settings
Create Date: 2026-10-14

SCRUM-52 "Register for a confirmed event" (ADR-0032): one ``registrations`` row per
Attendee's place at an event, with a ``registration_status`` and when it was made. The
foreign keys to ``event_requests`` and ``users`` are database-level only. The unique
pair (event, attendee) keeps AC3, that nobody registers twice, whatever the service
checks.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0027_create_registrations"
down_revision = "0026_add_registration_settings"
branch_labels = None
depends_on = None

#: Only ``registered`` is written so far; SCRUM-53 adds ``withdrawn`` (ADR-0032).
STATUS_VALUES = ("registered",)


def upgrade() -> None:
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_request_id", sa.Integer(), nullable=False),
        sa.Column("attendee_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*STATUS_VALUES, name="registration_status"),
            nullable=False,
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attendee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_request_id",
            "attendee_id",
            name="uq_registrations_event_request_id_attendee_id",
        ),
    )
    op.create_index(
        op.f("ix_registrations_attendee_id"), "registrations", ["attendee_id"], unique=False
    )
    op.create_index(
        op.f("ix_registrations_event_request_id"),
        "registrations",
        ["event_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_registrations_attendee_id"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_event_request_id"), table_name="registrations")
    op.drop_table("registrations")
    # The PostgreSQL enum type is not dropped by drop_table; remove it
    # explicitly so a downgrade/upgrade cycle can recreate it.
    sa.Enum(name="registration_status").drop(op.get_bind(), checkfirst=True)
