"""Create event equipment lines table (events module).

Revision ID: 0011_create_equipment_lines
Revises: 0010_add_coordinator_assignment
Create Date: 2026-09-25

SCRUM-37 "Record what equipment an event needs" (ADR-0019): one
``event_equipment_lines`` row per equipment type an event needs, with a quantity of
at least 1, optional technical notes and an ``event_equipment_line_status``. The
foreign keys to ``event_requests`` and ``equipment_types`` are database-level only.
``notification_kind`` gains ``equipment_requested`` for AC5.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_create_equipment_lines"
down_revision = "0010_add_coordinator_assignment"
branch_labels = None
depends_on = None

#: Only ``requested`` is written so far; SCRUM-46 adds ``reserved`` (ADR-0019).
LINE_STATUS_VALUES = ("requested",)

#: What exists after migration 0010. Downgrade rebuilds ``notification_kind`` with just
#: this.
PREVIOUS_KIND_VALUES = ("event_request_submitted", "coordinator_assigned")

#: Added here (SCRUM-37 AC5).
ADDED_KIND_VALUES = ("equipment_requested",)


def upgrade() -> None:
    op.create_table(
        "event_equipment_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_request_id", sa.Integer(), nullable=False),
        sa.Column("equipment_type_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*LINE_STATUS_VALUES, name="event_equipment_line_status"),
            nullable=False,
        ),
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
        sa.CheckConstraint("quantity >= 1", name="ck_event_equipment_lines_quantity_min"),
        sa.ForeignKeyConstraint(["equipment_type_id"], ["equipment_types.id"]),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_request_id",
            "equipment_type_id",
            name="uq_event_equipment_lines_event_request_id_equipment_type_id",
        ),
    )
    op.create_index(
        op.f("ix_event_equipment_lines_equipment_type_id"),
        "event_equipment_lines",
        ["equipment_type_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_equipment_lines_event_request_id"),
        "event_equipment_lines",
        ["event_request_id"],
        unique=False,
    )
    # Postgres won't let a transaction use an enum value it added itself (and before
    # version 12 refuses ADD VALUE inside a transaction at all), so the addition runs
    # outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_KIND_VALUES:
            op.execute(
                sa.text("ALTER TYPE notification_kind ADD VALUE :value").bindparams(value=value)
            )


def downgrade() -> None:
    # Postgres can't remove enum values, so the type is rebuilt with the original list
    # and the column re-cast. A notification of the removed kind has no kind to go
    # back to, so it is deleted: a lossy rollback, like 0006's (ADR-0012).
    op.execute(sa.text("DELETE FROM notifications WHERE kind = 'equipment_requested'"))
    op.execute(sa.text("ALTER TYPE notification_kind RENAME TO notification_kind_old"))
    sa.Enum(*PREVIOUS_KIND_VALUES, name="notification_kind").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE notifications ALTER COLUMN kind "
            "TYPE notification_kind USING kind::text::notification_kind"
        )
    )
    op.execute(sa.text("DROP TYPE notification_kind_old"))

    op.drop_index(
        op.f("ix_event_equipment_lines_event_request_id"), table_name="event_equipment_lines"
    )
    op.drop_index(
        op.f("ix_event_equipment_lines_equipment_type_id"), table_name="event_equipment_lines"
    )
    op.drop_table("event_equipment_lines")
    # The PostgreSQL enum type is not dropped by drop_table; remove it
    # explicitly so a downgrade/upgrade cycle can recreate it.
    sa.Enum(name="event_equipment_line_status").drop(op.get_bind(), checkfirst=True)
