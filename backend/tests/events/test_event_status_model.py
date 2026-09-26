"""Unit tests for SCRUM-22 "Define the event status model".

AC1: an event request holds exactly one of the story's seven statuses, and each one
survives a trip through the database. AC2: the status is shown by its value, and the
organiser who submitted a request can open it to see its current status. The other
four viewers in AC2 wait on later stories (ADR-0012). An unknown reference is a 404,
and a typed reference ignores case and spaces (ADR-0004). Which organisers may open
a request, and the 404 for everyone else, are SCRUM-7's
(``test_organisation_event_visibility.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.errors import AuthenticationError, AuthorizationError, NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.schemas import EventRequestSchema
from app.modules.events.services import get_event_request_for_organiser

pytestmark = pytest.mark.scrum_22

MakeEventRequest = Callable[..., EventRequest]

REFERENCE = "EVR-AAAAAAAA"
REQUEST_PATH = f"/api/events/requests/{REFERENCE}"


def _saved(db_session: Session, event_request: EventRequest) -> EventRequest:
    db_session.add(event_request)
    db_session.commit()
    return event_request


def _open_request(app: Flask, token: str | None) -> tuple[Response, int]:
    """Call the detail route as the holder of ``token``, or with no token at all."""
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    with app.test_request_context(REQUEST_PATH, headers=headers):
        return routes.get_my_request(reference=REFERENCE)


# --------------------------------------------------------------------------
# AC1 — exactly one of the seven statuses
# --------------------------------------------------------------------------


def test_status_values_are_exactly_the_seven_in_the_story() -> None:
    values = [status.value for status in EventRequestStatus]

    assert values == [
        "draft",
        "submitted",
        "under_review",
        "confirmed",
        "completed",
        "cancelled",
        "rejected",
    ]


@pytest.mark.parametrize("status", list(EventRequestStatus), ids=lambda status: status.value)
def test_every_status_round_trips_through_the_status_column(
    db_session: Session, make_event_request: MakeEventRequest, status: EventRequestStatus
) -> None:
    saved = _saved(db_session, make_event_request(status=status))
    db_session.expire_all()

    reloaded = db_session.get(EventRequest, saved.id)
    stored = db_session.execute(text("SELECT status FROM event_requests")).scalar_one()

    assert reloaded is not None
    assert reloaded.status is status
    assert stored == status.value


# --------------------------------------------------------------------------
# AC2 — the status is shown by its value
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", list(EventRequestStatus), ids=lambda status: status.value)
def test_every_status_is_shown_by_its_value(
    make_event_request: MakeEventRequest, status: EventRequestStatus
) -> None:
    dumped = EventRequestSchema().dump(make_event_request(status=status))

    assert dumped["status"] == status.value


# --------------------------------------------------------------------------
# AC2 — the organiser sees the current status of their own request
# --------------------------------------------------------------------------


def test_organiser_sees_the_current_status_of_their_own_request(
    db_session: Session, saved_users: list[User], make_event_request: MakeEventRequest
) -> None:
    event_request = make_event_request(
        reference=REFERENCE, status=EventRequestStatus.UNDER_REVIEW, organiser_id=7
    )
    saved = _saved(db_session, event_request)

    found = get_event_request_for_organiser("7", REFERENCE, session=db_session)

    assert found is saved
    assert found.status is EventRequestStatus.UNDER_REVIEW


def test_an_unknown_reference_is_not_found(
    db_session: Session, saved_users: list[User], make_event_request: MakeEventRequest
) -> None:
    _saved(db_session, make_event_request(reference=REFERENCE, organiser_id=7))

    with pytest.raises(NotFoundError) as exc_info:
        get_event_request_for_organiser("7", "EVR-ZZZZZZZZ", session=db_session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Event request not found."


@pytest.mark.parametrize("typed", ["evr-aaaaaaaa", " EVR-AAAAAAAA ", "Evr-Aaaaaaaa"])
def test_reference_lookup_ignores_case_and_surrounding_spaces(
    db_session: Session, saved_users: list[User], make_event_request: MakeEventRequest, typed: str
) -> None:
    saved = _saved(db_session, make_event_request(reference=REFERENCE, organiser_id=7))

    assert get_event_request_for_organiser("7", typed, session=db_session) is saved


# --------------------------------------------------------------------------
# Detail route — Event Organisers only, identified by their token
# --------------------------------------------------------------------------


def test_detail_route_allows_only_event_organisers() -> None:
    assert routes.get_my_request.allowed_roles == frozenset({"event_organiser"})  # type: ignore[attr-defined]


def test_other_roles_cannot_open_a_request(
    app: Flask,
    token_for: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
    non_organiser_role: Role,
) -> None:
    service = MagicMock()
    monkeypatch.setattr(routes, "get_event_record_for_organiser", service)

    with pytest.raises(AuthorizationError) as exc_info:
        _open_request(app, token_for(role=non_organiser_role))

    assert exc_info.value.status_code == 403
    service.assert_not_called()


def test_detail_without_a_token_is_401(app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    monkeypatch.setattr(routes, "get_event_record_for_organiser", service)

    with pytest.raises(AuthenticationError) as exc_info:
        _open_request(app, None)

    assert exc_info.value.status_code == 401
    service.assert_not_called()


def test_detail_route_returns_the_callers_request_with_its_status(
    app: Flask,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    monkeypatch: pytest.MonkeyPatch,
    make_event_request: MakeEventRequest,
) -> None:
    organiser = make_user(role=Role.EVENT_ORGANISER, user_id=7)
    calls: list[tuple[Any, Any]] = []

    def fake_get(organiser_id: Any, reference: Any) -> tuple[EventRequest, None]:
        calls.append((organiser_id, reference))
        event_request = make_event_request(reference=REFERENCE, status=EventRequestStatus.CONFIRMED)
        return event_request, None  # no coordinator assigned (SCRUM-30)

    monkeypatch.setattr(routes, "get_event_record_for_organiser", fake_get)

    response, status = _open_request(app, token_for(organiser))

    assert status == 200
    assert calls == [("7", REFERENCE)]
    body = response.get_json()
    assert body["reference"] == REFERENCE
    assert body["status"] == "confirmed"
    assert "id" not in body
    assert "organiser_id" not in body
