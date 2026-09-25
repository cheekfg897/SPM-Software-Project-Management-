"""Shared fixtures for the unit-test suite.

The suite is **unit tests only**: services, permissions and decorators are
exercised directly. No real Postgres, no Flask test client. Most service tests
use ``mock_session``; tests whose outcome depends on what a query selects use
``db_session``, an in-memory SQLite database. An application context is always
pushed because JWT creation and several rules read from ``app.config``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
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
from app.modules.venue.models import Venue, VenueOpeningPeriod


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
    Staff 4 and Event Organiser 7, who belongs to client organisation 3 so they can
    submit event requests (SCRUM-66).
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


@pytest.fixture()
def make_venue() -> Callable[..., Venue]:
    """Factory for ``Venue`` objects; add one to ``db_session`` to persist it.

    Setup and turnaround default to 0, so only tests that set them deal with buffers.
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
            opening_periods=opening_periods or [],
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
