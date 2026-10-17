"""Add the venue preparation details and their history kind.

Revision ID: 0033_add_venue_preparation
Revises: 0038_add_out_of_service_audit
Create Date: 2026-10-17

SCRUM-84 "Update venue preparation details" (ADR-0049):

* ``venue_booking_requests`` gains ``preparation_status`` (enum
  ``venue_preparation_status``, ``not_started`` for every existing row) and
  ``preparation_notes`` (AC1).
* ``event_history_entry_kind`` gains ``venue_preparation_updated``, written with each
  update so the user and the time are kept (AC4).

The history value is added outside the migration's transaction, with ``IF NOT EXISTS``,
as 0032 does. Downgrading drops the columns and their enum type, deletes the history
entries of the new kind and rebuilds the history type without it (lossy, like 0032's).

Numbered 0033 when written, but chained after 0038 (SCRUM-47), which merged first
after SCRUM-49's 0035; 0038 adds no history kind. SCRUM-85's migration (0034)
re-points its ``down_revision`` to this one, and its downgrade's list of previous
history kinds must then include this one's value.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0033_add_venue_preparation"
down_revision = "0038_add_out_of_service_audit"
branch_labels = None
depends_on = None

PREPARATION_STATUS_VALUES = ("not_started", "in_progress", "ready")

#: What migrations 0010-0035 left. Downgrade rebuilds ``event_history_entry_kind`` with
#: just this.
PREVIOUS_HISTORY_KIND_VALUES = (
    "coordinator_assigned",
    "coordinator_reassigned",
    "field_changed",
    "event_completed",
    "review_started",
    "decision_recorded",
    "clarification_requested",
    "clarification_answered",
    "venue_booking_requested",
    "equipment_reserved",
    "venue_arrangement_changed",
    "venue_arrangement_withdrawn",
    "equipment_outcome_recorded",
    "venue_booking_approved",
    "venue_booking_rejected",
    "safety_review_requested",
    "safety_outcome_recorded",
    "event_confirmed",
)

#: Added here (SCRUM-84 AC4).
ADDED_HISTORY_KIND_VALUE = "venue_preparation_updated"


def upgrade() -> None:
    preparation_status = sa.Enum(*PREPARATION_STATUS_VALUES, name="venue_preparation_status")
    preparation_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "venue_booking_requests",
        sa.Column(
            "preparation_status",
            preparation_status,
            nullable=False,
            server_default="not_started",
        ),
    )
    op.add_column("venue_booking_requests", sa.Column("preparation_notes", sa.Text()))

    # Postgres won't let a transaction use an enum value it added itself, so the
    # addition runs outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        op.execute(
            sa.text(
                "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS :value"
            ).bindparams(value=ADDED_HISTORY_KIND_VALUE)
        )


def downgrade() -> None:
    op.drop_column("venue_booking_requests", "preparation_notes")
    op.drop_column("venue_booking_requests", "preparation_status")
    sa.Enum(name="venue_preparation_status").drop(op.get_bind(), checkfirst=True)

    # Postgres can't remove an enum value, so the entries go first and the type is
    # rebuilt with its previous list and the table's ``kind`` column re-cast.
    op.execute(
        sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(
            value=ADDED_HISTORY_KIND_VALUE
        )
    )
    op.execute(
        sa.text("ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old")
    )
    sa.Enum(*PREVIOUS_HISTORY_KIND_VALUES, name="event_history_entry_kind").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE event_history_entries ALTER COLUMN kind"
            " TYPE event_history_entry_kind USING kind::text::event_history_entry_kind"
        )
    )
    op.execute(sa.text("DROP TYPE event_history_entry_kind_old"))
