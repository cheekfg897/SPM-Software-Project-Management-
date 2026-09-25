"""Business logic for the venue module.

Same shape as ``app.modules.auth.services``: routes call these functions, tests
call them directly, and other modules call them instead of touching the models.
Every function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.database import resolve_session
from app.common.errors import NotFoundError
from app.common.validation import load_or_raise
from app.modules.venue.models import Venue, VenueOpeningPeriod, join_list_field
from app.modules.venue.opening_hours import Period
from app.modules.venue.schemas import EditVenueSchema

_LIST_FIELDS = ("facilities", "accessibility_features", "supported_layouts")


def _build_periods(periods: Iterable[Period]) -> list[VenueOpeningPeriod]:
    return [VenueOpeningPeriod(**period._asdict()) for period in periods]


# --------------------------------------------------------------------------
# SCRUM-25 — catalogue CRUD, deactivate/reactivate
# --------------------------------------------------------------------------


def get_venue(venue_id: int, *, session: Session | None = None) -> Venue:
    """Fetch a venue by primary key, active or not.

    Raises:
        NotFoundError: if no such venue exists.
    """
    venue = resolve_session(session).get(Venue, venue_id)
    if venue is None:
        raise NotFoundError("Venue not found.")
    return venue


def list_venues(*, session: Session | None = None) -> list[Venue]:
    """Active venues only — a deactivated venue no longer appears here (AC5)."""
    stmt = select(Venue).where(Venue.is_active.is_(True)).order_by(Venue.name)
    return list(resolve_session(session).scalars(stmt).all())


def create_venue(payload: Mapping[str, Any] | None, *, session: Session | None = None) -> Venue:
    """Create a venue (SCRUM-25 AC1/AC2).

    Raises:
        ValidationError: 400 — missing/blank required fields or invalid values.
    """
    data = load_or_raise(EditVenueSchema(), payload)
    sess = resolve_session(session)

    venue = Venue(
        name=data["name"],
        location=data["location"],
        capacity=data["capacity"],
        facilities=join_list_field(data["facilities"]),
        accessibility_features=join_list_field(data["accessibility_features"]),
        supported_layouts=join_list_field(data["supported_layouts"]),
        opening_periods=_build_periods(data["opening_hours"]),
    )
    sess.add(venue)
    sess.commit()
    return venue


def update_venue(
    venue_id: int, payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> Venue:
    """Update a venue's editable fields (SCRUM-25 AC1/AC2).

    Only the fields present in ``payload`` are changed. ``opening_hours``, if
    present, replaces the whole weekly schedule (ADR-0008).

    Raises:
        NotFoundError: 404 — no such venue.
        ValidationError: 400 — invalid values for the supplied fields.
    """
    schema = EditVenueSchema()
    # Field names, not True: True would also let an incomplete period through.
    data = load_or_raise(schema, payload, partial=tuple(schema.fields))
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)

    if "opening_hours" in data:
        venue.opening_periods = _build_periods(data.pop("opening_hours"))
    for field in _LIST_FIELDS:
        if field in data:
            data[field] = join_list_field(data[field])
    for key, value in data.items():
        setattr(venue, key, value)

    sess.commit()
    return venue


def deactivate_venue(venue_id: int, *, session: Session | None = None) -> Venue:
    """Deactivate a venue (SCRUM-25 AC5): drops out of listing and search."""
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)
    venue.is_active = False
    sess.commit()
    return venue


def reactivate_venue(venue_id: int, *, session: Session | None = None) -> Venue:
    """Reactivate a previously deactivated venue (SCRUM-25 AC6)."""
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)
    venue.is_active = True
    sess.commit()
    return venue
