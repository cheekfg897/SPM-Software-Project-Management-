"""Fixtures for the events module tests."""

from __future__ import annotations

import importlib.util
import io
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.equipment.models import EquipmentType
from app.modules.events import routes
from app.modules.events.models import (
    EventEquipmentLine,
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    CoordinatorContact,
    EventEdit,
    EventRecord,
    decide_event_request,
    get_event_record_for_coordinator,
    get_event_record_for_organiser,
    reassign_coordinator,
    record_event_history,
    request_clarification,
    resubmit_event_request,
    save_draft_event_request,
    start_event_request_review,
    submit_event_request,
    update_event_request,
)
from app.modules.notifications.services import (
    NotificationKind,
    list_notifications_for_recipient,
)
from tests.events.cases import DRAFT_REFERENCE

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "versions"


#: Every role but Event Coordinator, in a fixed order so test ids are stable.
NON_COORDINATOR_ROLES = sorted(ALL_ROLES - {Role.EVENT_COORDINATOR}, key=lambda role: role.value)


@pytest.fixture(params=NON_COORDINATOR_ROLES, ids=lambda role: role.value)
def non_coordinator_role(request: pytest.FixtureRequest) -> Role:
    """Each role but Event Coordinator in turn, for routes only coordinators call."""
    return request.param


#: Every role but Event Organiser, in a fixed order so test ids are stable.
NON_ORGANISER_ROLES = sorted(ALL_ROLES - {Role.EVENT_ORGANISER}, key=lambda role: role.value)


@pytest.fixture(params=NON_ORGANISER_ROLES, ids=lambda role: role.value)
def non_organiser_role(request: pytest.FixtureRequest) -> Role:
    """Each role but Event Organiser in turn, for routes only organisers call."""
    return request.param


@pytest.fixture()
def integrity_error() -> Callable[[Exception], IntegrityError]:
    """Wrap ``orig`` in an ``IntegrityError`` as SQLAlchemy would raise it."""

    def _make(orig: Exception) -> IntegrityError:
        return IntegrityError("INSERT INTO event_requests ...", {}, orig)

    return _make


@pytest.fixture()
def references_in_order() -> Callable[..., Callable[[], str]]:
    """Factory for a reference factory that hands out given references, in order."""

    def _factory(*values: str) -> Callable[[], str]:
        remaining = iter(values)
        return lambda: next(remaining)

    return _factory


@pytest.fixture()
def other_organisers(
    saved_users: list[User], make_user: Callable[..., User], save: Callable[..., None]
) -> list[User]:
    """Save three more organisers: 8 and 6 of organisations 3 and 4, and unlinked 10.

    Alongside organiser 7 (``saved_users``), these give tests a colleague in the same
    organisation (8), one in another organisation (6), and an account SCRUM-66 has not
    linked to any organisation yet (10).
    """
    organisers = [
        make_user(
            email="organiser8@example.com", role=Role.EVENT_ORGANISER, user_id=8, organisation_id=3
        ),
        make_user(
            email="organiser6@example.com", role=Role.EVENT_ORGANISER, user_id=6, organisation_id=4
        ),
        make_user(email="organiser10@example.com", role=Role.EVENT_ORGANISER, user_id=10),
    ]
    save(*organisers)
    return organisers


@pytest.fixture()
def coordinator_three() -> CoordinatorContact:
    """Coordinator 3 of ``saved_users``, as the organiser sees them (SCRUM-24 AC7)."""
    return CoordinatorContact(full_name="Coordinator Three", email="coordinator3@example.com")


@pytest.fixture()
def today() -> date:
    """A fixed "today" so date rules don't depend on when the tests run."""
    return date(2026, 9, 15)


@pytest.fixture()
def valid_event_request_payload() -> dict[str, Any]:
    """A submission that satisfies every rule, with every field filled in."""
    return {
        "name": "ConnectSphere Partner Summit",
        "purpose": "Annual showcase for partner organisations",
        "description": "Keynotes in the morning, breakout sessions after lunch.",
        "proposed_date": "2026-10-15",
        "start_time": "09:00",
        "end_time": "17:00",
        "expected_attendance": 250,
        "venue_requirements": "Main hall with a stage and 3 breakout rooms",
        "accessibility_needs": "Step-free access and live captioning",
        "equipment_requirements": "2 projectors, PA system, 4 wireless mics",
        "registration_required": True,
    }


@pytest.fixture()
def submit_valid_request(
    db_session: Session, valid_event_request_payload: dict[str, Any], today: date
) -> Callable[..., EventRequest]:
    """Submit ``valid_event_request_payload`` as organiser 7 on ``db_session``.

    Hands out the given references in order (``EVR-AAAAAAAA`` if none are given), so
    a test can force a reference collision. The payload is the fixture's own dict, so
    a test may change it before submitting.
    """

    def _submit(*references: str) -> EventRequest:
        remaining = iter(references or ("EVR-AAAAAAAA",))
        return submit_event_request(
            7,
            valid_event_request_payload,
            session=db_session,
            today=today,
            reference_factory=lambda: next(remaining),
        )

    return _submit


@pytest.fixture()
def history_of(
    db_session: Session,
) -> Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]:
    """The saved history of an event request, oldest first (ADR-0018).

    Each entry as ``(kind, actor_id, details)``, read back from the database.
    """

    def _history(
        event_request_id: int,
    ) -> list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]:
        db_session.expire_all()
        stmt = (
            select(EventHistoryEntry)
            .where(EventHistoryEntry.event_request_id == event_request_id)
            .order_by(EventHistoryEntry.occurred_at, EventHistoryEntry.id)
        )
        entries = []
        for entry in db_session.scalars(stmt):
            entries.append((entry.kind, entry.actor_id, entry.details))
        return entries

    return _history


@pytest.fixture()
def lead_assigns(db_session: Session) -> Callable[[EventRequest, int], None]:
    """Give a submitted request its coordinator, as the Event Coordinator Lead does.

    Submission leaves a request unassigned (SCRUM-95 AC1), so a test whose own subject
    needs an assigned coordinator takes this step explicitly. It sets the column and
    nothing else; the audit entry and the notices belong to the Lead's own service,
    which SCRUM-95 tests where it lives.
    """

    def _assign(event_request: EventRequest, coordinator_id: int) -> None:
        event_request.coordinator_id = coordinator_id
        db_session.commit()

    return _assign


@pytest.fixture()
def coordinator_of(db_session: Session) -> Callable[[int], int | None]:
    """The coordinator a saved request is assigned to, read back from the database."""

    def _coordinator_of(event_request_id: int) -> int | None:
        db_session.expire_all()
        event_request = db_session.get(EventRequest, event_request_id)
        assert event_request is not None
        return event_request.coordinator_id

    return _coordinator_of


@pytest.fixture()
def organiser_is_found(mock_session: MagicMock, make_user: Callable[..., User]) -> None:
    """Make ``mock_session`` find organiser 7, linked to client organisation 3.

    Submitting looks up the organiser to copy their organisation (SCRUM-66 AC4).
    """
    mock_session.get.return_value = make_user(
        role=Role.EVENT_ORGANISER, user_id=7, organisation_id=3
    )


@pytest.fixture()
def load_migration() -> Callable[[str], ModuleType]:
    """Import a migration file from ``migrations/versions`` by its file name."""

    def _load(file_name: str) -> ModuleType:
        spec = importlib.util.spec_from_file_location(
            f"migration_{file_name[:4]}", MIGRATIONS_DIR / file_name
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return _load


@pytest.fixture()
def render_migration_sql() -> Callable[[Callable[[], None]], str]:
    """Render the SQL Alembic would run on Postgres for a migration step, offline.

    ``flask db check`` doesn't compare enum members, and the unit suite has no
    Postgres, so migration tests read the SQL instead.
    """

    def _render(operation: Callable[[], None]) -> str:
        buffer = io.StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql",
            opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True},
        )
        with Operations.context(context):
            operation()
        return buffer.getvalue()

    return _render


@pytest.fixture()
def assert_in_order() -> Callable[[str, list[str]], None]:
    """Check that every statement appears in rendered SQL, in the given order."""

    def _assert(sql: str, expected_in_order: list[str]) -> None:
        positions = [sql.find(statement) for statement in expected_in_order]
        assert -1 not in positions
        assert positions == sorted(positions)

    return _assert


@pytest.fixture()
def assert_migration_and_model_agree() -> Callable[
    [tuple[str, ...], tuple[str, ...], set[str]], None
]:
    """Check that an enum migration's previous and added values are all in the model.

    Pass the migration's previous values, the values it adds, and the model's values.
    """

    def _assert(
        previous_values: tuple[str, ...], added_values: tuple[str, ...], model_values: set[str]
    ) -> None:
        previous = set(previous_values)
        added = set(added_values)

        # Subset, not equality: a later migration could add a further value this one
        # doesn't know about, as 0015 later did to 0010 and 0012's history kinds.
        assert previous | added <= model_values
        assert previous.isdisjoint(added)

    return _assert


#: The two notices an assignment raises: the new coordinator's (SCRUM-30 AC4) and the
#: organiser's (SCRUM-39 AC1, ADR-0030).
ASSIGNMENT_NOTIFICATION_KINDS = frozenset(
    {NotificationKind.COORDINATOR_ASSIGNED, NotificationKind.REQUEST_ASSIGNED}
)


@pytest.fixture()
def assignment_notices_of(
    notifications_of: Callable[[int], list[tuple[Any, ...]]],
) -> Callable[[int], list[NotificationKind]]:
    """The assignment notices a user has, newest first, and no other kind.

    Submitting a request raises neither of them any more (SCRUM-95 AC1): it is the
    Event Coordinator Lead's assignment that does. Other kinds still reach the same
    people on the same path, so a test about assignment asks only about these two
    rather than for an empty list.
    """

    def _assignment_notices_of(user_id: int) -> list[NotificationKind]:
        notices = []
        for _event_request_id, _reference, _name, kind, _read_at in notifications_of(user_id):
            if kind in ASSIGNMENT_NOTIFICATION_KINDS:
                notices.append(kind)
        return notices

    return _assignment_notices_of


@pytest.fixture()
def detailed_notifications_of() -> Callable[[int], list[tuple[Any, ...]]]:
    """A user's notifications, newest first, as (reference, kind, detail) rows.

    For notifications whose ``detail`` carries text, such as a decision's reason
    (SCRUM-31) or a clarification's question and answer (SCRUM-32).
    """

    def _detailed_notifications_of(user_id: int) -> list[tuple[Any, ...]]:
        rows = []
        for notification in list_notifications_for_recipient(user_id):
            rows.append((notification.event_reference, notification.kind, notification.detail))
        return rows

    return _detailed_notifications_of


@pytest.fixture()
def save_draft(db_session: Session) -> Callable[[int, dict[str, Any]], EventRequest]:
    """Save a draft through the service, always under ``DRAFT_REFERENCE`` (SCRUM-20).

    Runs on ``db_session``, so the draft is really persisted and can be read back or
    reopened by another service call in the same test.
    """

    def _save(organiser_id: int, payload: dict[str, Any]) -> EventRequest:
        return save_draft_event_request(
            organiser_id, payload, session=db_session, reference_factory=lambda: DRAFT_REFERENCE
        )

    return _save


@pytest.fixture()
def reload_event_request(db_session: Session) -> Callable[[int], EventRequest]:
    """Read an event request back from the database rather than the session's cache."""

    def _reload(event_request_id: int) -> EventRequest:
        db_session.expire_all()
        event_request = db_session.get(EventRequest, event_request_id)
        assert event_request is not None
        return event_request

    return _reload


@pytest.fixture()
def set_status(
    saved_event_request: EventRequest, save: Callable[..., None]
) -> Callable[[EventRequestStatus], None]:
    """Move ``saved_event_request`` to another status and save it."""

    def _set(status: EventRequestStatus) -> None:
        saved_event_request.status = status
        save(saved_event_request)

    return _set


@pytest.fixture()
def valid_equipment_line_payload(equipment_type: EquipmentType) -> dict[str, Any]:
    """An equipment line body that satisfies every rule: two of the saved type."""
    return {"equipment_type_id": equipment_type.id, "quantity": 2, "notes": "Needs HDMI"}


@pytest.fixture()
def event_needing(
    make_event_request: Callable[..., EventRequest],
    make_equipment_line: Callable[..., EventEquipmentLine],
    equipment_type: EquipmentType,
    save: Callable[..., None],
) -> Callable[..., EventRequest]:
    """Factory: save an event that needs two of ``equipment_type`` (a projector)."""

    def _save(
        reference: str = "EVR-AAAAAAAA",
        *,
        proposed_date: date = date(2026, 10, 15),
        start_time: time = time(9, 0),
        status: EventRequestStatus = EventRequestStatus.SUBMITTED,
    ) -> EventRequest:
        event_request = make_event_request(
            reference=reference, proposed_date=proposed_date, start_time=start_time, status=status
        )
        save(event_request)
        save(make_equipment_line(event_request, equipment_type))
        return event_request

    return _save


@pytest.fixture()
def shown_event(make_event_request: Callable[..., EventRequest]) -> EventRequest:
    """The in-memory event request that the API shows as ``event_as_shown``."""
    return make_event_request()


@pytest.fixture()
def event_as_shown() -> dict[str, Any]:
    """``shown_event`` as the equipment routes show it (ADR-0019).

    The same field names and formats as the event request itself.
    """
    return {
        "reference": "EVR-AAAAAAAA",
        "name": "Partner Summit",
        "proposed_date": "2026-10-15",
        "end_date": "2026-10-15",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
    }


@pytest.fixture()
def shown_line(
    shown_event: EventRequest,
    make_equipment_type: Callable[..., EquipmentType],
    make_equipment_line: Callable[..., EventEquipmentLine],
) -> EventEquipmentLine:
    """An in-memory line of ``shown_event`` that the API shows as ``line_as_shown``."""
    line = make_equipment_line(shown_event, make_equipment_type())
    # In-memory objects have no ids, so set the ones ``line_as_shown`` expects.
    line.id = 7
    line.equipment_type_id = 1
    return line


@pytest.fixture()
def line_as_shown() -> dict[str, Any]:
    """``shown_line`` as the API shows it (SCRUM-37 AC4)."""
    return {
        "id": 7,
        "equipment_type_id": 1,
        "quantity": 2,
        "notes": "Needs HDMI",
        "status": "requested",
    }


@pytest.fixture()
def reload_equipment_line(db_session: Session) -> Callable[[int], EventEquipmentLine]:
    """Read an equipment line back from the database rather than the session's cache."""

    def _reload(line_id: int) -> EventEquipmentLine:
        db_session.expire_all()
        line = db_session.get(EventEquipmentLine, line_id)
        assert line is not None
        return line

    return _reload


@pytest.fixture()
def edit_event(
    saved_users: list[User], saved_event_request: EventRequest, today: date
) -> Callable[[int, dict[str, Any] | None], EventEdit]:
    """Edit ``saved_event_request`` (``EVR-AAAAAAAA``) as ``actor_id`` (SCRUM-33).

    Runs against the default session, which ``db_session`` also yields, so a test can
    read back what was saved through either fixture.
    """

    def _edit(actor_id: int, payload: dict[str, Any] | None) -> EventEdit:
        return update_event_request(actor_id, "EVR-AAAAAAAA", payload, today=today)

    return _edit


@pytest.fixture()
def reassign(
    saved_users: list[User], saved_event_request: EventRequest
) -> Callable[[int, str], tuple[EventRequest, CoordinatorContact]]:
    """Reassign ``saved_event_request`` to the user with this email (SCRUM-87).

    The request, ``EVR-AAAAAAAA``, starts with Event Coordinator 3; ``actor_id`` is
    who reassigns it. Runs on ``db_session`` with ``saved_users``.
    """

    def _reassign(actor_id: int, coordinator_email: str) -> tuple[EventRequest, CoordinatorContact]:
        payload = {"coordinator_email": coordinator_email}
        return reassign_coordinator(actor_id, "EVR-AAAAAAAA", payload)

    return _reassign


@pytest.fixture()
def reassignment_lookups(
    mock_session: MagicMock,
    make_event_request: Callable[..., EventRequest],
    make_user: Callable[..., User],
) -> EventRequest:
    """Make ``mock_session`` find what a reassignment from coordinator 3 to 9 looks up.

    The request ``EVR-AAAAAAAA`` (id 1, with coordinator 3) by its reference, then
    coordinator 9 by email; either coordinator by id, for their name and email.
    Returns the request.
    """
    event_request = make_event_request(coordinator_id=3)
    event_request.id = 1
    coordinators = {}
    for user_id, name in [(3, "Three"), (9, "Nine")]:
        coordinators[user_id] = make_user(
            email=f"coordinator{user_id}@example.com",
            full_name=f"Coordinator {name}",
            role=Role.EVENT_COORDINATOR,
            user_id=user_id,
        )

    def get_coordinator(_model: type, user_id: int) -> User:
        return coordinators[user_id]

    mock_session.scalar.side_effect = [event_request, coordinators[9]]
    mock_session.get.side_effect = get_coordinator
    return event_request


@pytest.fixture()
def start_review(
    saved_users: list[User], saved_event_request: EventRequest
) -> Callable[[int], EventRequest]:
    """Move ``saved_event_request`` to under review as ``actor_id`` (SCRUM-31).

    The request, ``EVR-AAAAAAAA``, is submitted and assigned to Event Coordinator 3.
    Runs on ``db_session`` with ``saved_users``.
    """

    def _start(actor_id: int) -> EventRequest:
        return start_event_request_review(actor_id, "EVR-AAAAAAAA")

    return _start


@pytest.fixture()
def decide(
    saved_users: list[User], saved_event_request: EventRequest
) -> Callable[..., EventRequest]:
    """Decide ``saved_event_request`` as ``actor_id``, with a reason if one is given.

    The request, ``EVR-AAAAAAAA``, is submitted and assigned to Event Coordinator 3
    (SCRUM-31). Runs on ``db_session`` with ``saved_users``.
    """

    def _decide(actor_id: int, outcome: str, reason: str | None = None) -> EventRequest:
        payload = {"outcome": outcome}
        if reason is not None:
            payload["reason"] = reason
        return decide_event_request(actor_id, "EVR-AAAAAAAA", payload)

    return _decide


@pytest.fixture()
def assert_status_unchanged(
    saved_event_request: EventRequest,
    reload_event_request: Callable[[int], EventRequest],
    history_of: Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]],
) -> Callable[[EventRequestStatus], None]:
    """Check ``saved_event_request`` still has this status and no history was written.

    For SCRUM-31's refusals: a review or a decision that is refused changes nothing.
    """

    def _assert(status: EventRequestStatus) -> None:
        assert reload_event_request(saved_event_request.id).status is status
        assert history_of(saved_event_request.id) == []

    return _assert


@pytest.fixture()
def under_review_request(
    saved_event_request: EventRequest, set_status: Callable[[EventRequestStatus], None]
) -> EventRequest:
    """``saved_event_request`` (``EVR-AAAAAAAA``), under review with Coordinator 3.

    Set directly, so its history is still empty (SCRUM-32).
    """
    set_status(EventRequestStatus.UNDER_REVIEW)
    return saved_event_request


@pytest.fixture()
def ask_clarification(
    saved_users: list[User], under_review_request: EventRequest
) -> Callable[[int, Any], EventRequest]:
    """Ask the organiser about ``under_review_request`` as ``actor_id`` (SCRUM-32).

    Runs on ``db_session`` with ``saved_users``; the payload is passed on as it is.
    """

    def _ask(actor_id: int, payload: Any) -> EventRequest:
        return request_clarification(actor_id, "EVR-AAAAAAAA", payload)

    return _ask


@pytest.fixture()
def awaiting_clarification_request(
    saved_event_request: EventRequest, set_status: Callable[[EventRequestStatus], None]
) -> EventRequest:
    """``saved_event_request`` (``EVR-AAAAAAAA``), awaiting the organiser's answer.

    Set directly, so its history is still empty (SCRUM-32).
    """
    set_status(EventRequestStatus.AWAITING_CLARIFICATION)
    return saved_event_request


@pytest.fixture()
def resubmit(
    saved_users: list[User], saved_event_request: EventRequest, today: date
) -> Callable[[int, Any], EventRequest]:
    """Answer and resubmit ``saved_event_request`` (``EVR-AAAAAAAA``) as ``actor_id``.

    SCRUM-32. The request is left in whatever status the test gives it; runs on
    ``db_session`` with ``saved_users``, and the payload is passed on as it is.
    """

    def _resubmit(actor_id: int, payload: Any) -> EventRequest:
        return resubmit_event_request(actor_id, "EVR-AAAAAAAA", payload, today=today)

    return _resubmit


@pytest.fixture(
    params=[(get_event_record_for_organiser, 7), (get_event_record_for_coordinator, 3)],
    ids=["organiser", "coordinator"],
)
def open_record(
    request: pytest.FixtureRequest, saved_users: list[User]
) -> Callable[[], EventRecord]:
    """Open ``EVR-AAAAAAAA``'s record as organiser 7, then as its coordinator, 3.

    For the sections both views of the record show (SCRUM-31, SCRUM-32; ADR-0026).
    """
    get_record, viewer_id = request.param

    def _open() -> EventRecord:
        return get_record(viewer_id, "EVR-AAAAAAAA")

    return _open


@pytest.fixture()
def open_record_route(
    call_route: Callable[..., Any],
    replace_services: Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]],
    token_for: Callable[..., str],
    make_user: Callable[..., User],
) -> Callable[[EventRecord], dict[str, Any]]:
    """Call the record route for ``EVR-AAAAAAAA`` as organiser 7, returning ``record``.

    The service is replaced, so the test checks only how the route shows the record.
    """
    token = token_for(make_user(role=Role.EVENT_ORGANISER, user_id=7))

    def _open(record: EventRecord) -> dict[str, Any]:
        replace_services(routes, {"get_event_record_for_organiser": record})
        response, status = call_route(
            "events.get_my_request",
            "GET",
            "/api/events/requests/EVR-AAAAAAAA",
            {"reference": "EVR-AAAAAAAA"},
            token,
        )
        assert status == 200
        return response.get_json()

    return _open


@pytest.fixture()
def record_entry(saved_event_request: EventRequest, db_session: Session) -> Callable[..., None]:
    """Save a history entry of ``kind`` on ``saved_event_request`` at a pinned time.

    Written directly, so tests can pin times out of insertion order.
    """

    def _record(
        kind: EventHistoryKind,
        occurred_at: datetime,
        *,
        actor_id: int,
        details: dict[str, Any] | None,
    ) -> None:
        record_event_history(
            saved_event_request,
            kind,
            actor_id=actor_id,
            details=details,
            session=db_session,
            now=occurred_at,
        )
        db_session.commit()

    return _record
