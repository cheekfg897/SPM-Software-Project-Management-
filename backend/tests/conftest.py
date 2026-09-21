"""Shared fixtures for the unit-test suite.

Sprint 1 tests are **unit tests only**: services, permissions and decorators
are exercised directly with a mocked database session. No real Postgres, no
Flask test client. An application context is still needed because JWT
creation and the password policy read from ``app.config``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_jwt_extended import create_access_token
from sqlalchemy.orm import Session

from app import create_app
from app.common.decorators import ROLE_CLAIM
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.venue.models import Booking, BookingStatus, Venue, VenueBlock


@pytest.fixture(scope="session")
def app() -> Flask:
    """A single app instance for the whole session (testing config)."""
    return create_app("testing")


@pytest.fixture(autouse=True)
def app_context(app: Flask) -> Iterator[None]:
    """Push an application context around every test."""
    with app.app_context():
        yield


@pytest.fixture()
def mock_session() -> MagicMock:
    """A stand-in for ``db.session``.

    Defaults: ``scalar()`` returns ``None`` (no existing user), ``get()``
    returns ``None``. Tests override ``return_value`` as needed and assert on
    ``add`` / ``commit`` / ``rollback`` calls.
    """
    session = MagicMock(spec=Session)
    session.scalar.return_value = None
    session.get.return_value = None
    return session


@pytest.fixture()
def make_user() -> Callable[..., User]:
    """Factory for in-memory ``User`` objects (never persisted)."""
    counter = {"id": 0}

    def _make(
        *,
        email: str = "alice@example.com",
        password: str = "Password123",
        full_name: str = "Alice Example",
        role: Role | str = Role.ATTENDEE,
        organisation: str | None = "Example Org",
        user_id: int | None = None,
    ) -> User:
        counter["id"] += 1
        user = User(
            email=email,
            full_name=full_name,
            role=Role(role),
            organisation=organisation,
        )
        user.id = user_id if user_id is not None else counter["id"]
        user.set_password(password)
        return user

    return _make


@pytest.fixture()
def valid_registration_payload() -> dict[str, Any]:
    """A registration body that satisfies every rule in ``RegisterSchema``."""
    return {
        "email": "New.User@Example.com",
        "password": "Str0ngPass",
        "full_name": "New User",
        "role": Role.EVENT_ORGANISER.value,
        "organisation": "Acme Events",
    }


@pytest.fixture()
def token_for() -> Callable[..., str]:
    """Factory that mints an access token for a user (or an arbitrary role)."""

    def _token(user: User | None = None, *, role: Role | str | None = None, **kwargs: Any) -> str:
        if user is not None:
            identity = str(user.id)
            role_value = user.role.value
        else:
            identity = "999"
            role_value = Role(role).value if role is not None else None
        claims = {ROLE_CLAIM: role_value} if role_value is not None else {}
        return create_access_token(identity=identity, additional_claims=claims, **kwargs)

    return _token


@pytest.fixture()
def make_venue() -> Callable[..., Venue]:
    """Factory for in-memory ``Venue`` objects (never persisted)."""

    counter = {"id": 0}

    def _make(
        *,
        name: str = "Main Hall",
        location: str = "Building A",
        capacity: int = 100,
        facilities: str = "projector,wifi",
        accessibility_features: str = "wheelchair_access",
        supported_layouts: str = "theatre,classroom",
        operating_hours_start: str = "09:00",
        operating_hours_end: str = "18:00",
        setup_minutes: int = 30,
        turnaround_minutes: int = 30,
        is_active: bool = True,
        venue_id: int | None = None,
    ) -> Venue:
        counter["id"] += 1
        venue = Venue(
            name=name,
            location=location,
            capacity=capacity,
            facilities=facilities,
            accessibility_features=accessibility_features,
            supported_layouts=supported_layouts,
            operating_hours_start=operating_hours_start,
            operating_hours_end=operating_hours_end,
            setup_minutes=setup_minutes,
            turnaround_minutes=turnaround_minutes,
            is_active=is_active,
        )
        venue.id = venue_id if venue_id is not None else counter["id"]
        return venue

    return _make


@pytest.fixture()
def make_booking() -> Callable[..., Booking]:
    """Factory for in-memory ``Booking`` objects (never persisted)."""

    counter = {"id": 0}

    def _make(
        *,
        venue_id: int = 1,
        event_id: int | None = None,
        start_time: datetime = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        end_time: datetime = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
        status: BookingStatus = BookingStatus.CONFIRMED,
        booking_id: int | None = None,
    ) -> Booking:
        counter["id"] += 1
        booking = Booking(
            venue_id=venue_id,
            event_id=event_id,
            start_time=start_time,
            end_time=end_time,
            status=status,
        )
        booking.id = booking_id if booking_id is not None else counter["id"]
        return booking

    return _make


@pytest.fixture()
def make_venue_block() -> Callable[..., VenueBlock]:
    """Factory for in-memory ``VenueBlock`` objects (never persisted)."""

    counter = {"id": 0}

    def _make(
        *,
        venue_id: int = 1,
        start_time: datetime = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc),
        end_time: datetime = datetime(2026, 1, 2, 11, 0, tzinfo=timezone.utc),
        reason: str = "Maintenance",
        block_id: int | None = None,
    ) -> VenueBlock:
        counter["id"] += 1
        block = VenueBlock(venue_id=venue_id, start_time=start_time, end_time=end_time, reason=reason)
        block.id = block_id if block_id is not None else counter["id"]
        return block

    return _make
