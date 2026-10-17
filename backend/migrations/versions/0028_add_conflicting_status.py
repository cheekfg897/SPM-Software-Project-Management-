"""Add the conflicting status to booking requests and bookings.

Revision ID: 0028_add_conflicting_status
Revises: 0027_create_registrations
Create Date: 2026-10-16

SCRUM-44 "Prevent the same venue being booked twice" (ADR-0045):

* ``booking_request_status`` gains ``conflicting``, for a Pending request that clashes
  with one Venue Staff approved.
* ``booking_status`` gains ``conflicting``, for a confirmed booking that a change to the
  venue's setup or turnaround time made overlap another booking or a block.
* ``uq_venue_booking_requests_pending`` covers Conflicting requests as well as Pending
  ones, so a coordinator can't raise a second request for the same event, venue and
  period while the first is Conflicting (SCRUM-42 AC6).

The values are added outside the migration's transaction, with ``IF NOT EXISTS``, as
0025 does. Postgres can't remove an enum value, so downgrading puts every Conflicting
row back to what it was before (a request to ``pending``, a booking to ``confirmed``)
and rebuilds both types without the value.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0028_add_conflicting_status"
down_revision = "0027_create_registrations"
branch_labels = None
depends_on = None

#: What migrations 0020, 0023 and 0025 left. Downgrade rebuilds
#: ``booking_request_status`` with just this.
PREVIOUS_REQUEST_STATUS_VALUES = ("pending", "withdrawn", "approved", "rejected")

#: What migration 0004 left. Downgrade rebuilds ``booking_status`` with just this.
PREVIOUS_BOOKING_STATUS_VALUES = ("tentative", "confirmed", "cancelled")


#: Which requests the index counts. The first is what migrations 0020 and 0023 left,
#: which downgrade restores; the second is what this migration makes it.
PENDING_ONLY = "status = 'pending'"
PENDING_OR_CONFLICTING = "status IN ('pending', 'conflicting')"


def _drop_pending_index() -> None:
    op.drop_index("uq_venue_booking_requests_pending", table_name="venue_booking_requests")


def _create_pending_index(predicate: str) -> None:
    op.create_index(
        "uq_venue_booking_requests_pending",
        "venue_booking_requests",
        ["event_id", "venue_id", "starts_at", "ends_at"],
        unique=True,
        postgresql_where=sa.text(predicate),
    )


def _add_conflicting(type_name: str) -> None:
    op.execute(sa.text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS 'conflicting'"))


def _rebuild_without_conflicting(
    type_name: str, table: str, previous_values: tuple[str, ...]
) -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the column re-cast.
    op.execute(sa.text(f"ALTER TYPE {type_name} RENAME TO {type_name}_old"))
    sa.Enum(*previous_values, name=type_name).create(op.get_bind())
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN status "
            f"TYPE {type_name} USING status::text::{type_name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {type_name}_old"))


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_conflicting("booking_request_status")
        _add_conflicting("booking_status")
    # The new value is committed by now, so the index can name it.
    _drop_pending_index()
    _create_pending_index(PENDING_OR_CONFLICTING)


def downgrade() -> None:
    # The pending index's predicate can't be re-created against the renamed enum type,
    # so it is dropped around the rebuild, as 0025 does. The wider index means no
    # Conflicting request shares its event, venue and period with a Pending one, so
    # turning them back into Pending ones cannot break the narrower index.
    _drop_pending_index()
    op.execute(
        sa.text("UPDATE venue_booking_requests SET status='pending' WHERE status = 'conflicting'")
    )
    _rebuild_without_conflicting(
        "booking_request_status", "venue_booking_requests", PREVIOUS_REQUEST_STATUS_VALUES
    )
    _create_pending_index(PENDING_ONLY)
    op.execute(sa.text("UPDATE bookings SET status='confirmed' WHERE status = 'conflicting'"))
    _rebuild_without_conflicting("booking_status", "bookings", PREVIOUS_BOOKING_STATUS_VALUES)
