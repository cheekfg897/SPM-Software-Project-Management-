"""Unit tests for SCRUM-19 "Submit an event request" — saving, references, listing and routes.

Covers AC1 (every field is saved) and AC5 (status Submitted, a reference, and
the request shows up in the organiser's list). Payload rules for AC1-AC4 are
in ``test_submit_event_request_validation.py``. Reference format and collision
handling follow ADR-0004.
"""

from __future__ import annotations

import re
from datetime import date, time
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from app.common.errors import AuthorizationError, ValidationError
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import (
    REFERENCE_UNIQUE_CONSTRAINT,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import EventRequestSchema
from app.modules.events.services import (
    MAX_REFERENCE_ATTEMPTS,
    ReferenceGenerationError,
    generate_reference,
    is_reference_collision,
    list_event_requests_for_organiser,
    submit_event_request,
)

pytestmark = pytest.mark.scrum_19

REFERENCE_PATTERN = re.compile(r"^EVR-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{8}$")
REQUESTS_PATH = "/api/events/requests"


class _DriverError(Exception):
    """Stands in for a psycopg2 error, which names the violated constraint on ``diag``."""

    def __init__(self, constraint_name: str | None, message: str = "integrity error") -> None:
        super().__init__(message)
        self.diag = SimpleNamespace(constraint_name=constraint_name)


def _integrity_error(orig: Exception) -> IntegrityError:
    return IntegrityError("INSERT INTO event_requests ...", {}, orig)


def _references(*values: str) -> Callable[[], str]:
    """A reference factory that hands out ``values`` in order."""
    remaining = iter(values)
    return lambda: next(remaining)


def _saved_request(**overrides: Any) -> EventRequest:
    fields: dict[str, Any] = {
        "reference": "EVR-AAAAAAAA",
        "status": EventRequestStatus.SUBMITTED,
        "organiser_id": 7,
        "name": "Partner Summit",
        "proposed_date": date(2026, 10, 15),
        "end_date": date(2026, 10, 15),
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "expected_attendance": 250,
        "registration_required": False,
    }
    fields.update(overrides)
    return EventRequest(**fields)


# --------------------------------------------------------------------------
# AC1 + AC5 — submitting saves every field with status Submitted and a reference
# --------------------------------------------------------------------------


def test_submission_is_saved_with_every_field_status_and_reference(
    mock_session: MagicMock, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    event_request = submit_event_request(
        "7", valid_event_request_payload, session=mock_session, today=today
    )

    assert isinstance(event_request, EventRequest)
    assert event_request.organiser_id == 7  # token identity string → int
    assert event_request.status is EventRequestStatus.SUBMITTED
    assert REFERENCE_PATTERN.match(event_request.reference)

    assert event_request.name == "ConnectSphere Partner Summit"
    assert event_request.purpose == "Annual showcase for partner organisations"
    assert event_request.description == "Keynotes in the morning, breakout sessions after lunch."
    assert event_request.proposed_date == date(2026, 10, 15)
    assert event_request.end_date == date(2026, 10, 15)
    assert event_request.start_time == time(9, 0)
    assert event_request.end_time == time(17, 0)
    assert event_request.expected_attendance == 250
    assert event_request.venue_requirements == "Main hall with a stage and 3 breakout rooms"
    assert event_request.accessibility_needs == "Step-free access and live captioning"
    assert event_request.equipment_requirements == "2 projectors, PA system, 4 wireless mics"
    assert event_request.registration_required is True

    mock_session.add.assert_called_once_with(event_request)
    mock_session.commit.assert_called_once()
    mock_session.rollback.assert_not_called()


def test_invalid_submission_is_not_saved(
    mock_session: MagicMock, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["proposed_date"] = "2026-09-14"  # yesterday

    with pytest.raises(ValidationError):
        submit_event_request("7", valid_event_request_payload, session=mock_session, today=today)

    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()


def test_each_submission_gets_its_own_reference(
    mock_session: MagicMock, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    first = submit_event_request("7", valid_event_request_payload, session=mock_session, today=today)
    second = submit_event_request("7", valid_event_request_payload, session=mock_session, today=today)

    assert first.reference != second.reference


def test_generated_references_match_the_adr_format() -> None:
    references = {generate_reference() for _ in range(500)}

    assert all(REFERENCE_PATTERN.match(ref) for ref in references)
    assert not set("".join(references)) & set("01OIL")  # no look-alike characters


# --------------------------------------------------------------------------
# ADR-0004 — reference collisions are retried, other failures are not
# --------------------------------------------------------------------------


def test_reference_collision_is_retried_with_a_new_reference(
    mock_session: MagicMock, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    collision = _integrity_error(_DriverError(REFERENCE_UNIQUE_CONSTRAINT))
    mock_session.commit.side_effect = [collision, None]

    event_request = submit_event_request(
        "7",
        valid_event_request_payload,
        session=mock_session,
        today=today,
        reference_factory=_references("EVR-AAAAAAAA", "EVR-BBBBBBBB"),
    )

    assert event_request.reference == "EVR-BBBBBBBB"
    assert mock_session.add.call_count == 2
    assert mock_session.commit.call_count == 2
    mock_session.rollback.assert_called_once()


def test_collision_on_every_attempt_but_the_last_still_succeeds(
    mock_session: MagicMock, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    collision = _integrity_error(_DriverError(REFERENCE_UNIQUE_CONSTRAINT))
    mock_session.commit.side_effect = [collision] * (MAX_REFERENCE_ATTEMPTS - 1) + [None]

    event_request = submit_event_request(
        "7",
        valid_event_request_payload,
        session=mock_session,
        today=today,
        reference_factory=_references("EVR-AAAAAAAA", "EVR-BBBBBBBB", "EVR-CCCCCCCC"),
    )

    assert event_request.reference == "EVR-CCCCCCCC"
    assert mock_session.rollback.call_count == MAX_REFERENCE_ATTEMPTS - 1


def test_collision_on_every_attempt_gives_up(
    mock_session: MagicMock, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    collision = _integrity_error(_DriverError(REFERENCE_UNIQUE_CONSTRAINT))
    mock_session.commit.side_effect = [collision] * MAX_REFERENCE_ATTEMPTS

    with pytest.raises(ReferenceGenerationError) as exc_info:
        submit_event_request(
            "7",
            valid_event_request_payload,
            session=mock_session,
            today=today,
            reference_factory=_references("EVR-AAAAAAAA", "EVR-BBBBBBBB", "EVR-CCCCCCCC"),
        )

    assert exc_info.value.status_code == 500
    assert mock_session.commit.call_count == MAX_REFERENCE_ATTEMPTS
    assert mock_session.rollback.call_count == MAX_REFERENCE_ATTEMPTS


def test_other_integrity_errors_are_not_retried(
    mock_session: MagicMock, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    """A new reference can't fix, say, an organiser id that doesn't exist."""
    mock_session.commit.side_effect = _integrity_error(
        _DriverError("event_requests_organiser_id_fkey")
    )

    with pytest.raises(IntegrityError):
        submit_event_request("7", valid_event_request_payload, session=mock_session, today=today)

    mock_session.commit.assert_called_once()
    mock_session.rollback.assert_called_once()


@pytest.mark.parametrize(
    ("orig", "expected"),
    [
        (_DriverError(REFERENCE_UNIQUE_CONSTRAINT), True),
        (_DriverError("uq_some_other_constraint"), False),
        (_DriverError(None, "no constraint reported"), False),
        (Exception("UNIQUE constraint failed: event_requests.reference"), True),  # SQLite
        (Exception("FOREIGN KEY constraint failed"), False),
    ],
)
def test_is_reference_collision(orig: Exception, expected: bool) -> None:
    assert is_reference_collision(_integrity_error(orig)) is expected


# --------------------------------------------------------------------------
# AC5 — the organiser's list
# --------------------------------------------------------------------------


def test_list_returns_the_requests_found(mock_session: MagicMock) -> None:
    rows = [_saved_request(reference="EVR-BBBBBBBB"), _saved_request(reference="EVR-AAAAAAAA")]
    mock_session.scalars.return_value = rows

    assert list_event_requests_for_organiser("7", session=mock_session) == rows


def test_list_is_empty_when_the_organiser_has_no_requests(mock_session: MagicMock) -> None:
    mock_session.scalars.return_value = []

    assert list_event_requests_for_organiser("7", session=mock_session) == []


def test_list_only_queries_the_callers_requests_newest_first(mock_session: MagicMock) -> None:
    mock_session.scalars.return_value = []

    list_event_requests_for_organiser("7", session=mock_session)

    stmt = mock_session.scalars.call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE event_requests.organiser_id = 7" in compiled
    assert "ORDER BY event_requests.created_at DESC, event_requests.id DESC" in compiled


def test_response_shows_reference_and_status_but_not_internal_ids(
    mock_session: MagicMock, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    event_request = submit_event_request(
        "7", valid_event_request_payload, session=mock_session, today=today
    )

    dumped = EventRequestSchema().dump(event_request)

    assert dumped["reference"] == event_request.reference
    assert dumped["status"] == "submitted"
    assert dumped["name"] == "ConnectSphere Partner Summit"
    assert dumped["proposed_date"] == "2026-10-15"
    assert dumped["end_date"] == "2026-10-15"
    assert dumped["start_time"] == "09:00:00"
    assert dumped["end_time"] == "17:00:00"
    assert dumped["expected_attendance"] == 250
    assert dumped["registration_required"] is True
    assert "id" not in dumped
    assert "organiser_id" not in dumped


# --------------------------------------------------------------------------
# Routes — only Event Organisers, and the organiser is always the caller
# --------------------------------------------------------------------------


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("view", [routes.submit_request, routes.list_my_requests])
def test_routes_allow_only_event_organisers(view: Callable[..., Any]) -> None:
    assert view.allowed_roles == frozenset({"event_organiser"})  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "role", sorted((r for r in Role if r is not Role.EVENT_ORGANISER), key=lambda r: r.value)
)
@pytest.mark.parametrize(
    ("method", "view"), [("POST", routes.submit_request), ("GET", routes.list_my_requests)]
)
def test_other_roles_are_forbidden(
    app: Flask, token_for, role: Role, method: str, view: Callable[..., Any]
) -> None:
    with app.test_request_context(
        REQUESTS_PATH, method=method, json={}, headers=_auth_headers(token_for(role=role))
    ):
        with pytest.raises(AuthorizationError):
            view()


def test_submit_route_uses_the_callers_id_and_returns_201(
    app: Flask,
    token_for,
    make_user,
    monkeypatch: pytest.MonkeyPatch,
    valid_event_request_payload: dict[str, Any],
) -> None:
    organiser = make_user(role=Role.EVENT_ORGANISER, user_id=7)
    calls: list[tuple[Any, Any]] = []

    def fake_submit(organiser_id: Any, payload: Any) -> EventRequest:
        calls.append((organiser_id, payload))
        return _saved_request()

    monkeypatch.setattr(routes, "submit_event_request", fake_submit)

    with app.test_request_context(
        REQUESTS_PATH,
        method="POST",
        json=valid_event_request_payload,
        headers=_auth_headers(token_for(organiser)),
    ):
        response, status = routes.submit_request()

    assert status == 201
    assert calls == [("7", valid_event_request_payload)]
    body = response.get_json()
    assert body["reference"] == "EVR-AAAAAAAA"
    assert body["status"] == "submitted"


def test_list_route_returns_the_callers_requests(
    app: Flask, token_for, make_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    organiser = make_user(role=Role.EVENT_ORGANISER, user_id=7)
    calls: list[Any] = []

    def fake_list(organiser_id: Any) -> list[EventRequest]:
        calls.append(organiser_id)
        return [_saved_request()]

    monkeypatch.setattr(routes, "list_event_requests_for_organiser", fake_list)

    with app.test_request_context(
        REQUESTS_PATH, method="GET", headers=_auth_headers(token_for(organiser))
    ):
        response, status = routes.list_my_requests()

    assert status == 200
    assert calls == ["7"]
    listed = response.get_json()["event_requests"]
    assert [(r["reference"], r["status"]) for r in listed] == [("EVR-AAAAAAAA", "submitted")]
