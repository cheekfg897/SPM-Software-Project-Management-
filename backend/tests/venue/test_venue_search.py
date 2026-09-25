"""Unit tests for SCRUM-35 — Search and filter venues against event requirements.

The search runs against ``db_session``, so the capacity, active and availability
filters are real SQL: flipping ``>=`` to ``<=`` or dropping a filter fails a test here.
AC4's message and who may search are checked through the registered route.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from flask import Flask, Response
from sqlalchemy.orm import Session

from app.common.errors import AuthenticationError, AuthorizationError, ValidationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.models import Booking, BookingStatus, Venue, VenueBlock

pytestmark = pytest.mark.scrum_35

MakeVenue = Callable[..., Venue]
MakeBooking = Callable[..., Booking]
MakeBlock = Callable[..., VenueBlock]
Save = Callable[..., None]

UTC = timezone.utc
NO_MATCHES_MESSAGE = "No venues match your search criteria."
OTHER_ROLES = sorted(ALL_ROLES - {Role.EVENT_COORDINATOR}, key=lambda role: role.value)


def _at(hour: int) -> datetime:
    """A moment on 1 October 2026, in UTC."""
    return datetime(2026, 10, 1, hour, 0, tzinfo=UTC)


#: The period every search asks for: 1 October, 10:00 to 12:00 UTC.
SEARCH_START, SEARCH_END = _at(10), _at(12)
BASE_SEARCH: dict[str, Any] = {
    "start_time": "2026-10-01T10:00:00Z",
    "end_time": "2026-10-01T12:00:00Z",
    "min_capacity": 1,
}


def _found(**filters: Any) -> list[str]:
    """Names of the venues a search with these filters returns, in result order."""
    matches = services.search_venues({**BASE_SEARCH, **filters})
    return [match.venue.name for match in matches]


def _search_route(app: Flask, token: str, payload: dict[str, Any]) -> tuple[Response, int]:
    headers = {"Authorization": f"Bearer {token}"}
    with app.test_request_context(
        "/api/venues/search", method="POST", json=payload, headers=headers
    ):
        return app.view_functions["venue.search_venues"]()


# --------------------------------------------------------------------------
# AC1 — the filters
# --------------------------------------------------------------------------


def test_capacity_must_reach_the_minimum(
    db_session: Session, make_venue: MakeVenue, save: Save
) -> None:
    save(
        make_venue(name="Small", capacity=99),
        make_venue(name="Exact", capacity=100),
        make_venue(name="Large", capacity=150),
    )

    assert _found(min_capacity=100) == ["Exact", "Large"]


def test_deactivated_venues_are_never_found(
    db_session: Session, make_venue: MakeVenue, save: Save
) -> None:
    save(make_venue(name="Open"), make_venue(name="Closed", is_active=False))

    assert _found() == ["Open"]


def test_location_matches_any_part_ignoring_case(
    db_session: Session, make_venue: MakeVenue, save: Save
) -> None:
    save(
        make_venue(name="East", location="Building B - East Wing"),
        make_venue(name="Other", location="Building C"),
    )

    assert _found(location="  building b ") == ["East"]


def test_location_wildcard_characters_are_matched_literally(
    db_session: Session, make_venue: MakeVenue, save: Save
) -> None:
    save(make_venue(name="Hall", location="Building A"))

    assert _found(location="%") == []
    assert _found(location="_") == []


def test_every_required_facility_must_be_offered(
    db_session: Session, make_venue: MakeVenue, save: Save
) -> None:
    save(
        make_venue(name="Partial", facilities="projector"),
        make_venue(name="Full", facilities="projector,stage,wifi"),
    )

    assert _found(required_facilities=["Projector", " stage "]) == ["Full"]


def test_every_required_accessibility_feature_must_be_offered(
    db_session: Session, make_venue: MakeVenue, save: Save
) -> None:
    save(
        make_venue(name="Partial", accessibility_features="wheelchair_access"),
        make_venue(name="Full", accessibility_features="wheelchair_access,hearing_loop"),
    )

    assert _found(required_accessibility=["Hearing_Loop", "wheelchair_access"]) == ["Full"]


def test_the_required_layout_must_be_supported(
    db_session: Session, make_venue: MakeVenue, save: Save
) -> None:
    save(
        make_venue(name="Theatre", supported_layouts="theatre,classroom"),
        make_venue(name="Boardroom", supported_layouts="boardroom"),
    )

    assert _found(required_layout="theatre") == ["Theatre"]


def test_results_are_ordered_by_name(
    db_session: Session, make_venue: MakeVenue, save: Save
) -> None:
    save(make_venue(name="Cedar"), make_venue(name="Annex"), make_venue(name="Birch"))

    assert _found() == ["Annex", "Birch", "Cedar"]


# --------------------------------------------------------------------------
# AC2 — only venues free for the whole period
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [BookingStatus.CONFIRMED, BookingStatus.TENTATIVE])
def test_a_booking_or_hold_overlapping_the_period_rules_the_venue_out(
    db_session: Session, venue: Venue, make_booking: MakeBooking, save: Save, status: BookingStatus
) -> None:
    save(make_booking(venue, _at(11), _at(13), status=status))

    assert _found() == []


def test_a_cancelled_booking_does_not_rule_the_venue_out(
    db_session: Session, venue: Venue, make_booking: MakeBooking, save: Save
) -> None:
    save(make_booking(venue, _at(10), _at(12), status=BookingStatus.CANCELLED))

    assert _found() == [venue.name]


def test_a_block_overlapping_the_period_rules_the_venue_out(
    db_session: Session, venue: Venue, make_block: MakeBlock, save: Save
) -> None:
    save(make_block(venue, _at(9), _at(11)))

    assert _found() == []


def test_periods_that_only_touch_the_search_do_not_overlap(
    db_session: Session, venue: Venue, make_booking: MakeBooking, make_block: MakeBlock, save: Save
) -> None:
    """A booking ending at 10:00 and a block from 12:00 leave 10:00-12:00 free."""
    save(make_booking(venue, _at(8), SEARCH_START), make_block(venue, SEARCH_END, _at(14)))

    assert _found() == [venue.name]


def test_another_venues_bookings_do_not_rule_this_one_out(
    db_session: Session, make_venue: MakeVenue, make_booking: MakeBooking, save: Save
) -> None:
    free, busy = make_venue(name="Free"), make_venue(name="Busy")
    save(free, busy)
    save(make_booking(busy, _at(10), _at(12)))

    assert _found() == ["Free"]


# --------------------------------------------------------------------------
# AC3 — what each result shows
# --------------------------------------------------------------------------


def test_a_result_shows_the_venue_and_the_requirements_it_meets(
    app: Flask,
    db_session: Session,
    make_venue: MakeVenue,
    save: Save,
    token_for: Callable[..., str],
) -> None:
    venue = make_venue(
        name="Grand Hall",
        capacity=300,
        location="Building B",
        facilities="projector,wifi",
        accessibility_features="hearing_loop",
        supported_layouts="theatre",
    )
    save(venue)
    payload = {
        **BASE_SEARCH,
        "required_facilities": ["Projector"],
        "required_accessibility": ["hearing_loop"],
        "required_layout": "theatre",
    }

    response, status = _search_route(app, token_for(role=Role.EVENT_COORDINATOR), payload)

    assert status == 200
    assert response.get_json() == {
        "results": [
            {
                "id": venue.id,
                "name": "Grand Hall",
                "capacity": 300,
                "location": "Building B",
                "matched_requirements": {
                    "facilities": ["projector"],
                    "accessibility_features": ["hearing_loop"],
                    "layout": "theatre",
                },
            }
        ]
    }


# --------------------------------------------------------------------------
# AC4 — a clear message when nothing matches
# --------------------------------------------------------------------------


def test_an_empty_search_says_nothing_matched(
    app: Flask, db_session: Session, token_for: Callable[..., str]
) -> None:
    response, status = _search_route(app, token_for(role=Role.EVENT_COORDINATOR), BASE_SEARCH)

    assert status == 200
    assert response.get_json() == {"results": [], "message": NO_MATCHES_MESSAGE}


# --------------------------------------------------------------------------
# Who can search — Event Coordinators only (the story's Roles field)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_only_event_coordinators_can_search(
    app: Flask, db_session: Session, token_for: Callable[..., str], role: Role
) -> None:
    with pytest.raises(AuthorizationError):
        _search_route(app, token_for(role=role), BASE_SEARCH)


def test_searching_needs_a_signed_in_user(app: Flask, db_session: Session) -> None:
    with app.test_request_context("/api/venues/search", method="POST", json=BASE_SEARCH):
        with pytest.raises(AuthenticationError):
            app.view_functions["venue.search_venues"]()


# --------------------------------------------------------------------------
# Validation of the search itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize("min_capacity", [0, -1])
def test_min_capacity_must_be_at_least_one(db_session: Session, min_capacity: int) -> None:
    with pytest.raises(ValidationError) as exc_info:
        services.search_venues({**BASE_SEARCH, "min_capacity": min_capacity})

    assert exc_info.value.details == {"min_capacity": ["min_capacity must be a positive number."]}


def test_the_period_must_end_after_it_starts(db_session: Session) -> None:
    payload = {**BASE_SEARCH, "end_time": "2026-10-01T10:00:00Z"}

    with pytest.raises(ValidationError) as exc_info:
        services.search_venues(payload)

    assert exc_info.value.details == {"end_time": ["end_time must be after start_time."]}


@pytest.mark.parametrize("missing", ["start_time", "end_time", "min_capacity"])
def test_the_period_and_minimum_capacity_are_required(db_session: Session, missing: str) -> None:
    payload = dict(BASE_SEARCH)
    del payload[missing]

    with pytest.raises(ValidationError) as exc_info:
        services.search_venues(payload)

    assert missing in exc_info.value.details


def test_an_unknown_layout_is_rejected(db_session: Session) -> None:
    with pytest.raises(ValidationError) as exc_info:
        services.search_venues({**BASE_SEARCH, "required_layout": "ballroom"})

    assert "required_layout" in exc_info.value.details
