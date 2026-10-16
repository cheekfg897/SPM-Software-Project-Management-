"""Add the Safety Officer role, the safety_review status and its history kind.

Revision ID: 0029_add_safety_review
Revises: 0028_add_conflicting_status
Create Date: 2026-10-16

SCRUM-97 "Submit an event for operational safety check" (ADR-0047):

* ``user_role`` gains ``safety_officer``, the internal role that reviews events (AC7).
* ``event_request_status`` gains ``safety_review``, between ``approved`` and
  ``confirmed`` (AC1).
* ``event_history_entry_kind`` gains ``safety_review_requested``, written when the
  coordinator sends an event to Safety Review.

Numbered 0029 because SCRUM-44's 0028 (``0028_add_conflicting_status``) merged first;
this revises it. Every value is added outside the migration's
transaction, with ``IF NOT EXISTS``, as 0022 and 0025 do. Downgrading is lossy, like
0022's: the history entries of the new kind are deleted, an event in Safety Review
goes back to ``approved``, and a Safety Officer becomes an ``attendee``, the role with
no staff access, before each type is rebuilt without the new value.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0029_add_safety_review"
down_revision = "0028_add_conflicting_status"
branch_labels = None
depends_on = None

#: What migrations 0001 and 0022 left. Downgrade rebuilds ``user_role`` with just this.
PREVIOUS_ROLE_VALUES = (
    "event_organiser",
    "attendee",
    "event_coordinator",
    "venue_staff",
    "technical_support_staff",
    "event_coordinator_lead",
)

#: Added here (SCRUM-97 AC7).
ADDED_ROLE_VALUES = ("safety_officer",)

#: What migrations 0002, 0006, 0017 and 0018 left, in the order Postgres holds them.
#: Downgrade rebuilds ``event_request_status`` with just this.
PREVIOUS_STATUS_VALUES = (
    "submitted",
    "draft",
    "under_review",
    "confirmed",
    "completed",
    "cancelled",
    "rejected",
    "approved",
    "awaiting_clarification",
)

#: Added here (SCRUM-97 AC1).
ADDED_STATUS_VALUES = ("safety_review",)

#: What migrations 0010-0025 left. Downgrade rebuilds ``event_history_entry_kind`` with
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
)

#: Added here (SCRUM-97 AC1).
ADDED_HISTORY_KIND_VALUES = ("safety_review_requested",)

#: Migration 0014's check (SCRUM-20, ADR-0024), copied because migrations don't import
#: each other. Downgrade drops it and puts it back around the status re-type.
DETAILS_CHECK_NAME = "ck_event_requests_details_unless_draft"
DETAILS_CHECK_CONDITION = (
    "status = 'draft' OR (proposed_date IS NOT NULL AND end_date IS NOT NULL AND "
    "start_time IS NOT NULL AND end_time IS NOT NULL AND expected_attendance IS NOT NULL)"
)


def _add_enum_values(type_name: str, values: tuple[str, ...]) -> None:
    for value in values:
        op.execute(
            sa.text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS :value").bindparams(
                value=value
            )
        )


def _rename_old_type_and_create_previous(type_name: str, previous_values: tuple[str, ...]) -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its old list.
    op.execute(sa.text(f"ALTER TYPE {type_name} RENAME TO {type_name}_old"))
    sa.Enum(*previous_values, name=type_name).create(op.get_bind())


def _retype_column(type_name: str, table: str, column: str) -> None:
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE {type_name} USING {column}::text::{type_name}"
        )
    )


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("user_role", ADDED_ROLE_VALUES)
        _add_enum_values("event_request_status", ADDED_STATUS_VALUES)
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)


def downgrade() -> None:
    # The reverse of upgrade(): history kinds, then statuses, then roles.
    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    _rename_old_type_and_create_previous("event_history_entry_kind", PREVIOUS_HISTORY_KIND_VALUES)
    _retype_column("event_history_entry_kind", "event_history_entries", "kind")
    op.execute(sa.text("DROP TYPE event_history_entry_kind_old"))

    # An event in Safety Review goes back to the status it was sent from.
    op.execute(
        sa.text("UPDATE event_requests SET status = 'approved' WHERE status = 'safety_review'")
    )
    _rename_old_type_and_create_previous("event_request_status", PREVIOUS_STATUS_VALUES)
    # Postgres can't re-type a column that a check constraint compares.
    op.drop_constraint(DETAILS_CHECK_NAME, "event_requests", type_="check")
    _retype_column("event_request_status", "event_requests", "status")
    op.create_check_constraint(DETAILS_CHECK_NAME, "event_requests", DETAILS_CHECK_CONDITION)
    op.execute(sa.text("DROP TYPE event_request_status_old"))

    # A Safety Officer keeps their account but loses staff access.
    op.execute(sa.text("UPDATE users SET role = 'attendee' WHERE role = 'safety_officer'"))
    _rename_old_type_and_create_previous("user_role", PREVIOUS_ROLE_VALUES)
    _retype_column("user_role", "users", "role")
    op.execute(sa.text("DROP TYPE user_role_old"))
