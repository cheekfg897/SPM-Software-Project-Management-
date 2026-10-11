"""Create equipment reservations and out-of-service tables.

Revision ID: 0021_add_equipment_reservations
Revises: 0019_add_review_kinds
Create Date: 2026-10-10

SCRUM-46 "Reserve equipment" and SCRUM-45 "Check whether enough equipment is free"
(ADR-0037):

* ``equipment_reservations``: units of one equipment type held for one event's exact
  period, with a quantity of at least 1. Indexed by type and period for the
  availability calculation, and by event.
* ``equipment_out_of_service``: units recorded as damaged or under maintenance, with an
  ``out_of_service_reason``. A row counts against availability until ``resolved_at`` is
  set. SCRUM-45/46 only read it; SCRUM-47 writes it.
* ``event_history_entry_kind`` and ``notification_kind`` gain ``equipment_reserved``
  (the audit trail, and SCRUM-46 AC5).

Foreign keys to ``event_requests``, ``equipment_types`` and ``users`` are database-level
only. The enum values are added outside the migration's transaction, with
``IF NOT EXISTS``, as 0010, 0012, 0015 and 0019 do. Downgrading drops the tables and the
reason type, deletes the rows of the new kind and rebuilds both enum types without it
(lossy, like 0015's).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0021_add_equipment_reservations"
down_revision = "0019_add_review_kinds"
branch_labels = None
depends_on = None

OUT_OF_SERVICE_REASON_VALUES = ("damaged", "under_maintenance")

#: What migrations 0010, 0012, 0015, 0016, 0017 and 0018 created. Downgrade rebuilds
#: ``event_history_entry_kind`` with just this.
PREVIOUS_HISTORY_KIND_VALUES = (
    "coordinator_assigned",
    "coordinator_reassigned",
    "field_changed",
    "event_completed",
    "review_started",
    "decision_recorded",
    "clarification_requested",
    "clarification_answered",
)

#: Added here (the audit trail of a reservation).
ADDED_HISTORY_KIND_VALUES = ("equipment_reserved",)

#: What migrations 0009, 0010, 0011, 0015, 0017, 0018 and 0019 created. Downgrade
#: rebuilds ``notification_kind`` with just this.
PREVIOUS_NOTIFICATION_KIND_VALUES = (
    "event_request_submitted",
    "coordinator_assigned",
    "equipment_requested",
    "significant_change",
    "event_request_approved",
    "event_request_rejected",
    "clarification_requested",
    "clarification_answered",
    "request_assigned",
)

#: Added here (SCRUM-46 AC5).
ADDED_NOTIFICATION_KIND_VALUES = ("equipment_reserved",)


def _add_timestamps() -> list[sa.Column]:
    """The ``created_at`` and ``updated_at`` columns of ``equipment_reservations``.

    ``equipment_out_of_service`` has neither: its ``recorded_at`` and ``resolved_at``
    say when its units went out of service and came back.
    """
    return [
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
    ]


def _rebuild_enum(table: str, type_name: str, values: tuple[str, ...]) -> None:
    """Rebuild a Postgres enum type with ``values`` and re-cast the table's ``kind``."""
    op.execute(sa.text(f"ALTER TYPE {type_name} RENAME TO {type_name}_old"))
    sa.Enum(*values, name=type_name).create(op.get_bind())
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN kind TYPE {type_name} USING kind::text::{type_name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {type_name}_old"))


def upgrade() -> None:
    out_of_service_reason = postgresql.ENUM(
        *OUT_OF_SERVICE_REASON_VALUES, name="out_of_service_reason", create_type=False
    )
    out_of_service_reason.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "equipment_reservations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("equipment_type_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_by", sa.Integer(), nullable=False),
        *_add_timestamps(),
        sa.CheckConstraint("quantity >= 1", name="ck_equipment_reservations_quantity_min"),
        sa.ForeignKeyConstraint(["equipment_type_id"], ["equipment_types.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["event_requests.id"]),
        sa.ForeignKeyConstraint(["reserved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_equipment_reservations_event_id"),
        "equipment_reservations",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_equipment_reservations_type_period",
        "equipment_reservations",
        ["equipment_type_id", "starts_at", "ends_at"],
        unique=False,
    )

    op.create_table(
        "equipment_out_of_service",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("equipment_type_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reason", out_of_service_reason, nullable=False),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity >= 1", name="ck_equipment_out_of_service_quantity_min"),
        sa.ForeignKeyConstraint(["equipment_type_id"], ["equipment_types.id"]),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_equipment_out_of_service_equipment_type_id"),
        "equipment_out_of_service",
        ["equipment_type_id"],
        unique=False,
    )

    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_HISTORY_KIND_VALUES:
            op.execute(
                sa.text(
                    "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS :value"
                ).bindparams(value=value)
            )
        for value in ADDED_NOTIFICATION_KIND_VALUES:
            op.execute(
                sa.text("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS :value").bindparams(
                    value=value
                )
            )


def downgrade() -> None:
    # Postgres can't remove an enum value, so each type is rebuilt with its previous
    # list; rows of the removed kind are deleted first. Notifications, then history
    # entries, then the tables: the reverse of upgrade().
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    _rebuild_enum("notifications", "notification_kind", PREVIOUS_NOTIFICATION_KIND_VALUES)

    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    _rebuild_enum("event_history_entries", "event_history_entry_kind", PREVIOUS_HISTORY_KIND_VALUES)

    op.drop_index(
        op.f("ix_equipment_out_of_service_equipment_type_id"),
        table_name="equipment_out_of_service",
    )
    op.drop_table("equipment_out_of_service")
    op.drop_index("ix_equipment_reservations_type_period", table_name="equipment_reservations")
    op.drop_index(op.f("ix_equipment_reservations_event_id"), table_name="equipment_reservations")
    op.drop_table("equipment_reservations")
    # drop_table leaves the enum type behind; remove it so CI's downgrade -> upgrade
    # replay can recreate it.
    sa.Enum(name="out_of_service_reason").drop(op.get_bind(), checkfirst=True)
