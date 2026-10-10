"""Shared fixtures for the unit-test suite.

The suite is **unit tests only**: services, permissions and decorators are
exercised directly. No real Postgres, no Flask test client. Most service tests
use ``mock_session``; tests whose outcome depends on what a query selects use
``db_session``, an in-memory SQLite database. An application context is always
pushed because JWT creation and several rules read from ``app.config``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date, time
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_jwt_extended import create_access_token
from sqlalchemy.orm import Session

from app import create_app
from app.common.decorators import ROLE_CLAIM
from app.extensions import db
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventRequest,
    EventRequestStatus,
)
from app.modules.venue.models import Venue, VenueOpeningPeriod, Weekday


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
def call_route(app: Flask) -> Callable[..., Any]:
    """Call a registered view function as Flask would for one request.

    The route's real decorators run, so permission tests check the actual wiring.
    ``token`` of ``None`` sends no ``Authorization`` header. The body is always ``{}``:
    tests that call routes replace the services, so its contents don't matter.
    """

    def _call(
        endpoint: str, method: str, path: str, view_kwargs: dict[str, Any], token: str | None
    ) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        with app.test_request_context(path, method=method, headers=headers, json={}):
            return app.view_functions[endpoint](**view_kwargs)

    return _call


@pytest.fixture()
def replace_services(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]:
    """Replace functions of a services module with mocks returning the given values.

    Returns the mocks by function name, so a test can check which were called.
    """

    def _replace(module: ModuleType, returns: dict[str, Any]) -> dict[str, MagicMock]:
        mocks = {}
        for name, value in returns.items():
            mock = MagicMock(return_value=value)
            monkeypatch.setattr(module, name, mock)
            mocks[name] = mock
        return mocks

    return _replace


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
def db_session() -> Iterator[Session]:
    """The app's real session, on an empty in-memory SQLite database for each test.

    Use it when a test's outcome depends on what a query selects, such as a filter
    or an ordering. ``mock_session`` returns whatever the test queued regardless of
    the ``WHERE`` clause, so a wrong or missing filter would still pass.
    """
    db.create_all()
    yield db.session
    db.session.remove()
    db.drop_all()


@pytest.fixture()
def save(db_session: Session) -> Callable[..., None]:
    """Persist objects to ``db_session`` and commit, as a service would."""

    def _save(*objects: object) -> None:
        db_session.add_all(objects)
        db_session.commit()

    return _save


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
        organisation_id: int | None = None,
        user_id: int | None = None,
    ) -> User:
        counter["id"] += 1
        user = User(
            email=email,
            full_name=full_name,
            role=Role(role),
            organisation_id=organisation_id,
        )
        user.id = user_id if user_id is not None else counter["id"]
        user.set_password(password)
        return user

    return _make


@pytest.fixture()
def saved_users(db_session: Session, make_user: Callable[..., User]) -> list[User]:
    """Users of several roles, saved to ``db_session``.

    Event Coordinators 9 and 3 (saved in that order, so a query has to sort them),
    each with their own name so a test can tell which one it got (SCRUM-30), Venue
    Staff 4, Event Organiser 7, who belongs to client organisation 3 so they can
    submit event requests (SCRUM-66), and Technical Support Staff 5 and 2 (also saved
    out of order).
    """
    users = [
        make_user(
            email="coordinator9@example.com",
            full_name="Coordinator Nine",
            role=Role.EVENT_COORDINATOR,
            user_id=9,
        ),
        make_user(
            email="coordinator3@example.com",
            full_name="Coordinator Three",
            role=Role.EVENT_COORDINATOR,
            user_id=3,
        ),
        make_user(email="staff4@example.com", role=Role.VENUE_STAFF, user_id=4),
        make_user(
            email="organiser7@example.com",
            role=Role.EVENT_ORGANISER,
            user_id=7,
            organisation_id=3,
        ),
        make_user(email="techsupport5@example.com", role=Role.TECHNICAL_SUPPORT_STAFF, user_id=5),
        make_user(email="techsupport2@example.com", role=Role.TECHNICAL_SUPPORT_STAFF, user_id=2),
    ]
    db_session.add_all(users)
    db_session.commit()
    return users


@pytest.fixture()
def valid_registration_payload() -> dict[str, Any]:
    """A registration body that satisfies every rule in ``RegisterSchema``.

    An attendee, because an Event Organiser also needs an existing client organisation
    (SCRUM-66); ``tests/auth/test_registration_organisation.py`` covers that path.
    """
    return {
        "email": "New.User@Example.com",
        "password": "Str0ngPass",
        "full_name": "New User",
        "role": Role.ATTENDEE.value,
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
def valid_organisation_payload() -> dict[str, Any]:
    """A client organisation body that satisfies every required rule (SCRUM-66)."""
    return {
        "name": "Acme Events",
        "contact_name": "Alice Tan",
        "contact_email": "alice@acme.example",
    }


@pytest.fixture()
def organiser_registration_payload(
    valid_registration_payload: dict[str, Any],
) -> Callable[[Any], dict[str, Any]]:
    """Factory for an Event Organiser's registration body naming ``organisation_id``.

    Takes any value, so tests can send ids of the wrong type too (SCRUM-66).
    """

    def _payload(organisation_id: Any) -> dict[str, Any]:
        return {
            **valid_registration_payload,
            "role": Role.EVENT_ORGANISER.value,
            "organisation_id": organisation_id,
        }

    return _payload


def default_opening_periods() -> list[VenueOpeningPeriod]:
    """Every day 09:00 to 18:00, the same schedule ``EditVenueSchema`` defaults to."""
    return [
        VenueOpeningPeriod(open_day=day, open_time=time(9), close_day=day, close_time=time(18))
        for day in Weekday
    ]


@pytest.fixture()
def make_venue() -> Callable[..., Venue]:
    """Factory for ``Venue`` objects; add one to ``db_session`` to persist it.

    Setup and turnaround default to 0, so only tests that set them deal with buffers.
    Opening hours default to every day 09:00-18:00, as a venue created through the API
    has; pass ``opening_periods=[]`` for a venue that is closed all week.
    """
    counter = {"id": 0}

    def _make(
        *,
        name: str = "Main Hall",
        location: str = "Building A",
        capacity: int = 100,
        facilities: str = "projector,wifi",
        accessibility_features: str = "wheelchair_access",
        supported_layouts: str = "theatre,classroom",
        opening_periods: list[VenueOpeningPeriod] | None = None,
        setup_minutes: int = 0,
        turnaround_minutes: int = 0,
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
            opening_periods=(
                default_opening_periods() if opening_periods is None else opening_periods
            ),
            setup_minutes=setup_minutes,
            turnaround_minutes=turnaround_minutes,
            is_active=is_active,
        )
        venue.id = venue_id if venue_id is not None else counter["id"]
        return venue

    return _make


@pytest.fixture()
def venue(make_venue: Callable[..., Venue], save: Callable[..., None]) -> Venue:
    """One saved, active venue with default details."""
    saved = make_venue()
    save(saved)
    return saved


@pytest.fixture()
def make_equipment_type() -> Callable[..., EquipmentType]:
    """Factory for ``EquipmentType`` objects; add one to ``db_session`` to persist it.

    By default the equipment is kept in a store, not at a venue.
    """

    def _make(
        *,
        name: str = "Projector",
        description: str | None = None,
        total_quantity: int = 10,
        venue_id: int | None = None,
        store_name: str | None = "Central AV store",
    ) -> EquipmentType:
        return EquipmentType(
            name=name,
            description=description,
            total_quantity=total_quantity,
            venue_id=venue_id,
            store_name=store_name,
        )

    return _make


@pytest.fixture()
def equipment_type(
    make_equipment_type: Callable[..., EquipmentType], save: Callable[..., None]
) -> EquipmentType:
    """One saved equipment type with default details, kept in a store."""
    saved = make_equipment_type()
    save(saved)
    return saved


@pytest.fixture()
def make_event_request() -> Callable[..., EventRequest]:
    """Factory for in-memory ``EventRequest`` objects.

    Add one to ``db_session`` to persist it. By default it is organiser 7's, filed
    under client organisation 3 as ``saved_users`` links them (SCRUM-66 AC4).
    Everything but the parameters is fixed; tests about the other fields go through
    ``submit_event_request`` with ``valid_event_request_payload``. The event ends on
    the day it starts.
    """

    def _make(
        *,
        reference: str = "EVR-AAAAAAAA",
        status: EventRequestStatus = EventRequestStatus.SUBMITTED,
        organiser_id: int = 7,
        organisation_id: int | None = 3,
        coordinator_id: int | None = None,
        proposed_date: date = date(2026, 10, 15),
        start_time: time = time(9, 0),
    ) -> EventRequest:
        return EventRequest(
            reference=reference,
            status=status,
            organiser_id=organiser_id,
            organisation_id=organisation_id,
            coordinator_id=coordinator_id,
            name="Partner Summit",
            proposed_date=proposed_date,
            end_date=proposed_date,
            start_time=start_time,
            end_time=time(17, 0),
            expected_attendance=250,
            registration_required=False,
        )

    return _make


@pytest.fixture()
def saved_event_request(
    make_event_request: Callable[..., EventRequest], save: Callable[..., None]
) -> EventRequest:
    """Event request ``EVR-AAAAAAAA`` by organiser 7, ``submitted`` and saved.

    It is assigned to Event Coordinator 3, who may change its equipment (ADR-0019).
    """
    event_request = make_event_request(coordinator_id=3)
    save(event_request)
    return event_request


@pytest.fixture()
def make_equipment_line() -> Callable[..., EventEquipmentLine]:
    """Factory for ``EventEquipmentLine`` objects; add one to ``db_session`` to save."""

    def _make(
        event_request: EventRequest,
        equipment_type: EquipmentType,
        *,
        quantity: int = 2,
        notes: str | None = "Needs HDMI",
    ) -> EventEquipmentLine:
        return EventEquipmentLine(
            event_request_id=event_request.id,
            equipment_type_id=equipment_type.id,
            quantity=quantity,
            notes=notes,
            status=EquipmentLineStatus.REQUESTED,
        )

    return _make


@pytest.fixture()
def microphone(
    make_equipment_type: Callable[..., EquipmentType], save: Callable[..., None]
) -> EquipmentType:
    """A second saved equipment type, for events that need more than one."""
    saved = make_equipment_type(name="Microphone", total_quantity=20)
    save(saved)
    return saved
