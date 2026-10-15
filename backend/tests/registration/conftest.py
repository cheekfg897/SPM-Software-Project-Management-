"""Fixtures for the registration module tests (SCRUM-52)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events.models import EventRequest
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.services import MyRegistration, list_my_registrations

#: Every role but Attendee, in a fixed order so test ids are stable.
NON_ATTENDEE_ROLES = sorted(ALL_ROLES - {Role.ATTENDEE}, key=lambda role: role.value)


@pytest.fixture(params=NON_ATTENDEE_ROLES, ids=lambda role: role.value)
def non_attendee_role(request: pytest.FixtureRequest) -> Role:
    """Each role but Attendee in turn, for routes only attendees call."""
    return request.param


@pytest.fixture()
def make_registration(save: Callable[..., None], now: datetime) -> Callable[..., Registration]:
    """Factory for saved registrations; ``registered_at`` defaults to ``now``."""

    def _make(
        event: EventRequest, attendee_id: int, *, registered_at: datetime | None = None
    ) -> Registration:
        registration = Registration(
            event_request_id=event.id,
            attendee_id=attendee_id,
            status=RegistrationStatus.REGISTERED,
            registered_at=registered_at if registered_at is not None else now,
        )
        save(registration)
        return registration

    return _make


@pytest.fixture()
def my_registrations(db_session: Session, now: datetime) -> Callable[..., list[MyRegistration]]:
    """The registrations ``attendee_id`` sees for the query ``params``, at ``now``."""

    def _list(attendee_id: int | str, params: dict[str, str] | None = None) -> list[MyRegistration]:
        listing = list_my_registrations(attendee_id, params or {}, session=db_session, now=now)
        return listing.registrations

    return _list
