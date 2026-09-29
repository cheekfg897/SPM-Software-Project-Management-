"""Unit tests for SCRUM-36 — Check whether a venue suits an event.

Covers AC1 (a venue too small for the expected attendance), AC2 (each missing
requirement is named), AC3 (a venue that meets everything is suitable) and ADR-0017
(the check takes the requirements themselves and ignores whether a venue is active).
AC4, the justification on a booking request, is deferred to SCRUM-42 (ADR-0017).

The check runs against ``db_session``; who may check, and the response shape, are
tested through the registered route.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask, Response
from sqlalchemy.orm import Session

from app.common.errors import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.models import LayoutType, Venue

pytestmark = pytest.mark.scrum_36

MakeVenue = Callable[..., Venue]
Save = Callable[..., None]
SavedVenue = Callable[..., Venue]

#: The story's Roles field: Event Coordinators check, and Venue Staff check too.
CHECKING_ROLES = [Role.EVENT_COORDINATOR, Role.VENUE_STAFF]
OTHER_ROLES = sorted(ALL_ROLES - set(CHECKING_ROLES), key=lambda role: role.value)
BASE_REQUIREMENTS: dict[str, Any] = {"expected_attendance": 1}
CAPACITY_MESSAGE = "Expected attendance of 150 exceeds the venue's capacity of 100."


@pytest.fixture()
def saved_venue(make_venue: MakeVenue, save: Save) -> SavedVenue:
    """Factory for a venue with the given details, saved so the check can find it."""

    def _make(**details: Any) -> Venue:
        venue = make_venue(**details)
        save(venue)
        return venue

    return _make


def _reasons(venue: Venue, **requirements: Any) -> list[tuple[str, str]]:
    """Each reason the venue is unsuitable, as ``(requirement, message)`` pairs."""
    result = services.check_venue_suitability(venue.id, {**BASE_REQUIREMENTS, **requirements})
    return [(reason.requirement.value, reason.message) for reason in result.reasons]


def _check_route(
    app: Flask, token: str, venue_id: int, payload: dict[str, Any]
) -> tuple[Response, int]:
    headers = {"Authorization": f"Bearer {token}"}
    with app.test_request_context(
        f"/api/venues/{venue_id}/suitability", method="POST", json=payload, headers=headers
    ):
        return app.view_functions["venue.check_suitability"](venue_id=venue_id)


# --------------------------------------------------------------------------
# AC1 — a venue too small for the expected attendance
# --------------------------------------------------------------------------


def test_a_venue_smaller_than_the_expected_attendance_is_unsuitable_because_of_capacity(
    db_session: Session, venue: Venue
) -> None:
    assert _reasons(venue, expected_attendance=150) == [("capacity", CAPACITY_MESSAGE)]


@pytest.mark.parametrize(
    ("expected_attendance", "suitable"),
    [(100, True), (101, False)],
    ids=["exactly-fits", "one-too-many"],
)
def test_capacity_must_reach_the_expected_attendance(
    db_session: Session, venue: Venue, expected_attendance: int, suitable: bool
) -> None:
    """The ``venue`` fixture holds 100."""
    result = services.check_venue_suitability(
        venue.id, {"expected_attendance": expected_attendance}
    )

    assert result.suitable is suitable


# --------------------------------------------------------------------------
# AC2 — each requirement the venue doesn't meet is named
# --------------------------------------------------------------------------


def test_a_missing_accessibility_feature_is_named(
    db_session: Session, saved_venue: SavedVenue
) -> None:
    venue = saved_venue(accessibility_features="hearing_loop")

    assert _reasons(venue, required_accessibility=["Step-Free Access"]) == [
        ("accessibility", "The venue does not offer step-free access.")
    ]


def test_only_the_facilities_the_venue_lacks_are_named(
    db_session: Session, saved_venue: SavedVenue
) -> None:
    venue = saved_venue(facilities="projector")

    assert _reasons(venue, required_facilities=["projector", "stage"]) == [
        ("facilities", "The venue does not offer stage.")
    ]


def test_an_unsupported_layout_is_named(db_session: Session, saved_venue: SavedVenue) -> None:
    venue = saved_venue(supported_layouts="boardroom")

    assert _reasons(venue, required_layout="theatre") == [
        ("layout", "The venue does not support the theatre layout.")
    ]


@pytest.mark.parametrize("layout", LayoutType.values())
def test_a_venue_supporting_the_requested_layout_is_not_named_for_it(
    db_session: Session, saved_venue: SavedVenue, layout: str
) -> None:
    """Every ``LayoutType`` value is matched, not just the ones the other tests use."""
    venue = saved_venue(supported_layouts=layout)

    assert _reasons(venue, required_layout=layout) == []


def test_every_unmet_requirement_is_reported_capacity_first(
    db_session: Session, saved_venue: SavedVenue
) -> None:
    venue = saved_venue(
        capacity=100,
        facilities="wifi",
        accessibility_features="hearing_loop",
        supported_layouts="boardroom",
    )

    reasons = _reasons(
        venue,
        expected_attendance=150,
        required_facilities=["projector", "stage"],
        required_accessibility=["step-free access"],
        required_layout="theatre",
    )

    assert reasons == [
        ("capacity", CAPACITY_MESSAGE),
        ("facilities", "The venue does not offer projector."),
        ("facilities", "The venue does not offer stage."),
        ("accessibility", "The venue does not offer step-free access."),
        ("layout", "The venue does not support the theatre layout."),
    ]


# --------------------------------------------------------------------------
# AC3 — a venue that meets every requirement is suitable
# --------------------------------------------------------------------------


def test_a_venue_meeting_every_requirement_is_suitable(
    db_session: Session, saved_venue: SavedVenue
) -> None:
    venue = saved_venue(
        capacity=300,
        facilities="projector,wifi",
        accessibility_features="step-free access,hearing_loop",
        supported_layouts="theatre,classroom",
    )
    requirements = {
        "expected_attendance": 250,
        "required_facilities": [" Projector "],
        "required_accessibility": ["step-free access"],
        "required_layout": "theatre",
    }

    result = services.check_venue_suitability(venue.id, requirements)

    assert result.suitable is True
    assert result.reasons == []


# --------------------------------------------------------------------------
# The route — what the response says
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"expected_attendance": 150, "required_accessibility": ["step-free access"]},
            {
                "suitable": False,
                "reasons": [
                    {"requirement": "capacity", "message": CAPACITY_MESSAGE},
                    {
                        "requirement": "accessibility",
                        "message": "The venue does not offer step-free access.",
                    },
                ],
            },
        ),
        ({"expected_attendance": 100}, {"suitable": True, "reasons": []}),
    ],
    ids=["unsuitable", "suitable"],
)
def test_the_route_reports_suitability_and_every_reason(
    app: Flask,
    db_session: Session,
    venue: Venue,
    token_for: Callable[..., str],
    payload: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    token = token_for(role=Role.EVENT_COORDINATOR)

    response, status = _check_route(app, token, venue.id, payload)

    assert status == 200
    assert response.get_json() == expected


# --------------------------------------------------------------------------
# Who can check — Event Coordinators and Venue Staff, the story's Roles field
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", CHECKING_ROLES)
def test_event_coordinators_and_venue_staff_can_check_suitability(
    app: Flask, db_session: Session, venue: Venue, token_for: Callable[..., str], role: Role
) -> None:
    _, status = _check_route(app, token_for(role=role), venue.id, BASE_REQUIREMENTS)

    assert status == 200


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_other_roles_cannot_check_suitability(
    app: Flask, db_session: Session, venue: Venue, token_for: Callable[..., str], role: Role
) -> None:
    with pytest.raises(AuthorizationError):
        _check_route(app, token_for(role=role), venue.id, BASE_REQUIREMENTS)


def test_checking_needs_a_signed_in_user(app: Flask, db_session: Session, venue: Venue) -> None:
    with app.test_request_context(
        f"/api/venues/{venue.id}/suitability", method="POST", json=BASE_REQUIREMENTS
    ):
        with pytest.raises(AuthenticationError):
            app.view_functions["venue.check_suitability"](venue_id=venue.id)


# --------------------------------------------------------------------------
# Errors — an unknown venue, and invalid requirements
# --------------------------------------------------------------------------


def test_an_unknown_venue_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        services.check_venue_suitability(999, BASE_REQUIREMENTS)

    assert exc_info.value.status_code == 404


@pytest.mark.parametrize("expected_attendance", [0, -1])
def test_expected_attendance_must_be_at_least_one(
    db_session: Session, venue: Venue, expected_attendance: int
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        services.check_venue_suitability(venue.id, {"expected_attendance": expected_attendance})

    assert exc_info.value.details == {
        "expected_attendance": ["expected_attendance must be a positive number."]
    }


def test_expected_attendance_is_required(db_session: Session, venue: Venue) -> None:
    with pytest.raises(ValidationError) as exc_info:
        services.check_venue_suitability(venue.id, {"required_layout": "theatre"})

    assert "expected_attendance" in exc_info.value.details


def test_an_unknown_layout_is_rejected(db_session: Session, venue: Venue) -> None:
    with pytest.raises(ValidationError) as exc_info:
        services.check_venue_suitability(
            venue.id, {**BASE_REQUIREMENTS, "required_layout": "ballroom"}
        )

    assert "required_layout" in exc_info.value.details


# --------------------------------------------------------------------------
# ADR-0017 — whether a venue is active isn't part of suitability
# --------------------------------------------------------------------------


def test_a_deactivated_venue_is_checked_like_any_other(
    db_session: Session, saved_venue: SavedVenue
) -> None:
    venue = saved_venue(capacity=100, is_active=False)

    assert _reasons(venue, expected_attendance=150) == [("capacity", CAPACITY_MESSAGE)]
