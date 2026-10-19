"""Unit tests for SCRUM-69 "Enable registration for an event and set its capacity".

AC1: the assigned coordinator enables or disables registration, and when they don't
say, it follows the organiser's ``registration_required`` (ADR-0043). AC2: enabling
needs a capacity. AC3: the capacity is the organiser's number, not limited by the venue
booked for the event (customer answer A74). AC4: enabling needs a confirmed event. AC5:
the capacity can change after registration opens, but not below the number already
registered (SCRUM-52 adds the registrations it counts). AC7: a change records who made
it and when, in the event history. A capacity outside 1 to the largest Postgres integer
is refused, and only the event's own coordinator may change the settings.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, ``submitted``, assigned to Event Coordinator 3), so lookups are real
SQL; the commit tests use ``mock_session``. Every call pins ``now`` except the one test
of the default.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    CAPACITY_REQUIRED_MESSAGE,
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    REGISTRATION_NOT_CONFIRMED_MESSAGE,
    HistoryEntryAsShown,
    RegistrationNotEnablableError,
    list_event_history,
    update_registration_settings,
)
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.events.cases import NOT_CONFIRMED_STATUSES, Arrange

pytestmark = pytest.mark.scrum_69

Update = Callable[[int, dict[str, Any]], EventRequest]
SettingsOf = Callable[[], tuple[bool, int | None]]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
SetStatus = Callable[[EventRequestStatus], None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)

ENABLE_WITH_100 = {"registration_enabled": True, "registration_capacity": 100}

#: The largest capacity a Postgres ``INTEGER`` column holds.
LARGEST_CAPACITY = 2_147_483_647


def _field_change(field: str, previous_value: Any, new_value: Any) -> dict[str, Any]:
    """What a ``field_changed`` entry's details say about one registration field."""
    return {
        "field": field,
        "previous_value": previous_value,
        "new_value": new_value,
        "significant": False,
    }


@pytest.fixture()
def update(
    saved_users: list[User], saved_event_request: EventRequest, db_session: Session
) -> Update:
    """Change the settings of ``saved_event_request`` as ``actor_id`` at ``NOW``."""

    def _update(actor_id: int, payload: dict[str, Any]) -> EventRequest:
        return update_registration_settings(
            actor_id, REFERENCE, payload, session=db_session, now=NOW
        )

    return _update


@pytest.fixture()
def confirmed_event_request(
    set_status: SetStatus, saved_event_request: EventRequest
) -> EventRequest:
    """``saved_event_request``, moved to ``confirmed``."""
    set_status(EventRequestStatus.CONFIRMED)
    return saved_event_request


@pytest.fixture()
def organiser_wants_registration(
    saved_event_request: EventRequest, save: Callable[..., None]
) -> None:
    """Make ``saved_event_request`` one whose organiser asked for registration."""
    saved_event_request.registration_required = True
    save(saved_event_request)


@pytest.fixture()
def settings_of(
    saved_event_request: EventRequest, reload_event_request: Callable[[int], EventRequest]
) -> SettingsOf:
    """The saved request's ``(enabled, capacity)`` settings, read back."""

    def _settings() -> tuple[bool, int | None]:
        reloaded = reload_event_request(saved_event_request.id)
        return reloaded.registration_enabled, reloaded.registration_capacity

    return _settings


@pytest.fixture()
def register_attendees(
    saved_event_request: EventRequest, save: Callable[..., None]
) -> Callable[..., None]:
    """Register ``count`` attendees for an event, ``saved_event_request`` by default."""

    def _register(count: int, event: EventRequest | None = None) -> None:
        target = event if event is not None else saved_event_request
        for attendee_id in range(1, count + 1):
            save(
                Registration(
                    event_request_id=target.id,
                    attendee_id=attendee_id,
                    status=RegistrationStatus.REGISTERED,
                    registered_at=NOW,
                )
            )

    return _register


def _assert_capacity_required(refused: ValidationError) -> None:
    assert refused.status_code == 400
    assert refused.details == {"registration_capacity": [CAPACITY_REQUIRED_MESSAGE]}


# --------------------------------------------------------------------------
# AC1 — registration is enabled or disabled; the default follows the organiser
# --------------------------------------------------------------------------


def test_a_coordinator_enables_registration_with_a_capacity(
    update: Update, confirmed_event_request: EventRequest, settings_of: SettingsOf
) -> None:
    updated = update(COORDINATOR_ID, ENABLE_WITH_100)

    assert updated is confirmed_event_request
    assert settings_of() == (True, 100)


def test_a_coordinator_disables_registration_and_the_capacity_is_kept(
    update: Update, confirmed_event_request: EventRequest, settings_of: SettingsOf
) -> None:
    update(COORDINATOR_ID, ENABLE_WITH_100)

    update(COORDINATOR_ID, {"registration_enabled": False})

    assert settings_of() == (False, 100)


def test_enabled_defaults_to_on_when_the_organiser_required_registration(
    update: Update,
    confirmed_event_request: EventRequest,
    organiser_wants_registration: None,
    settings_of: SettingsOf,
) -> None:
    update(COORDINATOR_ID, {"registration_capacity": 100})

    assert settings_of() == (True, 100)


def test_enabled_defaults_to_off_when_the_organiser_did_not_require_registration(
    update: Update, confirmed_event_request: EventRequest, settings_of: SettingsOf
) -> None:
    update(COORDINATOR_ID, {"registration_capacity": 100})

    assert settings_of() == (False, 100)


def test_once_a_capacity_exists_leaving_enabled_out_keeps_the_coordinators_choice(
    update: Update,
    confirmed_event_request: EventRequest,
    organiser_wants_registration: None,
    settings_of: SettingsOf,
) -> None:
    """The organiser wanted registration, but the coordinator turned it off."""
    update(COORDINATOR_ID, {"registration_enabled": False, "registration_capacity": 100})

    update(COORDINATOR_ID, {"registration_capacity": 80})

    assert settings_of() == (False, 80)


# --------------------------------------------------------------------------
# AC2 — enabling needs a capacity
# --------------------------------------------------------------------------


def test_enabling_without_a_capacity_is_refused(
    update: Update, confirmed_event_request: EventRequest, settings_of: SettingsOf
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        update(COORDINATOR_ID, {"registration_enabled": True})

    _assert_capacity_required(exc_info.value)
    assert settings_of() == (False, None)


def test_the_default_does_not_enable_an_event_that_has_no_capacity(
    update: Update,
    confirmed_event_request: EventRequest,
    organiser_wants_registration: None,
    settings_of: SettingsOf,
) -> None:
    """The organiser wanted registration, but nothing says how many places there are."""
    with pytest.raises(ValidationError) as exc_info:
        update(COORDINATOR_ID, {})

    _assert_capacity_required(exc_info.value)
    assert settings_of() == (False, None)


@pytest.mark.parametrize("capacity", [0, -5, LARGEST_CAPACITY + 1])
def test_a_capacity_outside_one_to_the_largest_integer_is_refused(
    update: Update,
    confirmed_event_request: EventRequest,
    settings_of: SettingsOf,
    capacity: int,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        update(COORDINATOR_ID, {"registration_enabled": True, "registration_capacity": capacity})

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {
        "registration_capacity": ["Capacity must be between 1 and 2147483647."]
    }
    assert settings_of() == (False, None)


@pytest.mark.parametrize("capacity", [1, LARGEST_CAPACITY])
def test_the_smallest_and_largest_capacities_are_accepted(
    update: Update,
    confirmed_event_request: EventRequest,
    settings_of: SettingsOf,
    capacity: int,
) -> None:
    update(COORDINATOR_ID, {"registration_enabled": True, "registration_capacity": capacity})

    assert settings_of() == (True, capacity)


@pytest.mark.parametrize("body", [None, [], "enable"], ids=["nothing", "a-list", "a-string"])
def test_a_body_that_is_not_an_object_is_refused(
    update: Update, confirmed_event_request: EventRequest, body: Any
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        update(COORDINATOR_ID, body)

    assert exc_info.value.status_code == 400
    assert exc_info.value.message == "Request body must be a JSON object."


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"registration_capacity": "100"}, "registration_capacity"),
        ({"registration_capacity": 1.5}, "registration_capacity"),
        ({"registration_capacity": True}, "registration_capacity"),
        ({"registration_capacity": None}, "registration_capacity"),
        ({"registration_enabled": "yes"}, "registration_enabled"),
        ({"registration_enabled": None}, "registration_enabled"),
        ({"status": "confirmed"}, "status"),
    ],
    ids=[
        "capacity-as-text",
        "capacity-fraction",
        "capacity-boolean",
        "capacity-null",
        "enabled-as-text",
        "enabled-null",
        "unknown-field",
    ],
)
def test_a_value_of_the_wrong_kind_is_refused_on_its_field(
    update: Update,
    confirmed_event_request: EventRequest,
    settings_of: SettingsOf,
    payload: dict[str, Any],
    field: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        update(COORDINATOR_ID, payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details is not None
    assert set(exc_info.value.details) == {field}
    assert settings_of() == (False, None)


# --------------------------------------------------------------------------
# AC3 — the capacity is the organiser's number, whatever the venue holds
# --------------------------------------------------------------------------


def test_a_capacity_above_the_booked_venues_is_accepted(
    update: Update,
    confirmed_event_request: EventRequest,
    venue: Venue,
    arrange: Arrange,
    settings_of: SettingsOf,
) -> None:
    """The organiser may plan for more than the venue seats (customer answer A74)."""
    arrange(BookingRequestStatus.APPROVED)
    above_the_venue = venue.capacity + 1

    update(COORDINATOR_ID, {"registration_enabled": True, "registration_capacity": above_the_venue})

    assert settings_of() == (True, above_the_venue)


# --------------------------------------------------------------------------
# AC4 — registration is enabled only for a confirmed event
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", NOT_CONFIRMED_STATUSES, ids=lambda status: status.value)
def test_registration_cannot_be_enabled_for_an_event_that_is_not_confirmed(
    update: Update, set_status: SetStatus, settings_of: SettingsOf, status: EventRequestStatus
) -> None:
    set_status(status)

    with pytest.raises(RegistrationNotEnablableError) as exc_info:
        update(COORDINATOR_ID, ENABLE_WITH_100)

    assert (exc_info.value.status_code, exc_info.value.error_code) == (
        409,
        "registration_not_enablable",
    )
    assert exc_info.value.message == REGISTRATION_NOT_CONFIRMED_MESSAGE
    assert settings_of() == (False, None)


def test_the_default_does_not_enable_an_event_that_is_not_confirmed(
    update: Update,
    organiser_wants_registration: None,
    settings_of: SettingsOf,
) -> None:
    """The submitted event's organiser wanted registration, but it can't open yet."""
    with pytest.raises(RegistrationNotEnablableError):
        update(COORDINATOR_ID, {"registration_capacity": 100})

    assert settings_of() == (False, None)


def test_a_capacity_can_be_stored_for_an_event_that_is_not_confirmed_while_disabled(
    update: Update, settings_of: SettingsOf
) -> None:
    update(COORDINATOR_ID, {"registration_enabled": False, "registration_capacity": 100})

    assert settings_of() == (False, 100)


def test_the_status_rule_looks_at_the_settings_left_behind_not_at_what_was_sent(
    update: Update, confirmed_event_request: EventRequest, set_status: SetStatus
) -> None:
    """Raising the capacity of an enabled event that has since completed is refused."""
    update(COORDINATOR_ID, ENABLE_WITH_100)
    set_status(EventRequestStatus.COMPLETED)

    with pytest.raises(RegistrationNotEnablableError):
        update(COORDINATOR_ID, {"registration_capacity": 150})


def test_registration_can_be_disabled_whatever_the_status(
    update: Update,
    confirmed_event_request: EventRequest,
    set_status: SetStatus,
    settings_of: SettingsOf,
) -> None:
    update(COORDINATOR_ID, ENABLE_WITH_100)
    set_status(EventRequestStatus.COMPLETED)

    update(COORDINATOR_ID, {"registration_enabled": False})

    assert settings_of() == (False, 100)


# --------------------------------------------------------------------------
# AC5 — the capacity can change, but not below the number already registered
# --------------------------------------------------------------------------


def test_a_capacity_below_the_number_registered_is_refused(
    update: Update,
    confirmed_event_request: EventRequest,
    register_attendees: Callable[..., None],
    settings_of: SettingsOf,
) -> None:
    update(COORDINATOR_ID, ENABLE_WITH_100)
    register_attendees(5)

    with pytest.raises(ValidationError) as exc_info:
        update(COORDINATOR_ID, {"registration_capacity": 4})

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {
        "registration_capacity": ["Capacity cannot be lower than the 5 places already taken."]
    }
    assert settings_of() == (True, 100)


def test_a_capacity_equal_to_the_number_registered_is_accepted(
    update: Update,
    confirmed_event_request: EventRequest,
    register_attendees: Callable[..., None],
    settings_of: SettingsOf,
) -> None:
    update(COORDINATOR_ID, ENABLE_WITH_100)
    register_attendees(5)

    update(COORDINATOR_ID, {"registration_capacity": 5})

    assert settings_of() == (True, 5)


def test_a_capacity_below_the_number_registered_is_refused_while_registration_is_off(
    update: Update,
    confirmed_event_request: EventRequest,
    register_attendees: Callable[..., None],
    settings_of: SettingsOf,
) -> None:
    update(COORDINATOR_ID, ENABLE_WITH_100)
    register_attendees(5)

    with pytest.raises(ValidationError) as exc_info:
        update(COORDINATOR_ID, {"registration_enabled": False, "registration_capacity": 4})

    assert exc_info.value.details == {
        "registration_capacity": ["Capacity cannot be lower than the 5 places already taken."]
    }
    assert settings_of() == (True, 100)


def test_registration_can_be_turned_off_while_attendees_are_registered(
    update: Update,
    confirmed_event_request: EventRequest,
    register_attendees: Callable[..., None],
    settings_of: SettingsOf,
) -> None:
    update(COORDINATOR_ID, ENABLE_WITH_100)
    register_attendees(5)

    update(COORDINATOR_ID, {"registration_enabled": False})

    assert settings_of() == (False, 100)


def test_an_event_with_no_capacity_has_no_registrations_to_check_against(
    update: Update, confirmed_event_request: EventRequest, settings_of: SettingsOf
) -> None:
    update(COORDINATOR_ID, {"registration_enabled": False})

    assert settings_of() == (False, None)


def test_registrations_for_another_event_are_not_counted(
    update: Update,
    confirmed_event_request: EventRequest,
    register_attendees: Callable[..., None],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    settings_of: SettingsOf,
) -> None:
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=3)
    save(other_event)
    register_attendees(5, other_event)

    update(COORDINATOR_ID, {"registration_enabled": True, "registration_capacity": 2})

    assert settings_of() == (True, 2)


# --------------------------------------------------------------------------
# ADR-0043 — only the event's own coordinator, and the order of the checks
# --------------------------------------------------------------------------


def test_only_the_events_assigned_coordinator_may_change_the_settings(
    update: Update, confirmed_event_request: EventRequest, settings_of: SettingsOf
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        update(OTHER_COORDINATOR_ID, ENABLE_WITH_100)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert settings_of() == (False, None)


def test_an_unknown_reference_is_404(saved_users: list[User], db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        update_registration_settings(
            COORDINATOR_ID, "EVR-ZZZZZZZZ", ENABLE_WITH_100, session=db_session, now=NOW
        )

    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


def test_a_draft_is_not_found_by_its_coordinator(
    update: Update, set_status: SetStatus, settings_of: SettingsOf
) -> None:
    """Staff never see a draft (ADR-0024): a 409 would say that one exists."""
    set_status(EventRequestStatus.DRAFT)

    with pytest.raises(NotFoundError):
        update(COORDINATOR_ID, ENABLE_WITH_100)

    assert settings_of() == (False, None)


def test_ownership_is_checked_before_the_status(update: Update, set_status: SetStatus) -> None:
    """Another coordinator learns no more about a submitted event than an open one."""
    set_status(EventRequestStatus.SUBMITTED)

    with pytest.raises(NotFoundError):
        update(OTHER_COORDINATOR_ID, ENABLE_WITH_100)


def test_the_payload_is_checked_before_the_status(update: Update) -> None:
    """A submitted event enabled with no capacity is asked for a capacity first."""
    with pytest.raises(ValidationError):
        update(COORDINATOR_ID, {"registration_enabled": True})


# --------------------------------------------------------------------------
# AC7 — who changed the settings and when, saved with the change
# --------------------------------------------------------------------------


def test_a_change_records_who_made_it_and_when(
    update: Update, confirmed_event_request: EventRequest
) -> None:
    update(COORDINATOR_ID, ENABLE_WITH_100)

    history = list_event_history(COORDINATOR_ID, REFERENCE, viewer_role=Role.EVENT_COORDINATOR)
    assert history == [
        HistoryEntryAsShown(
            kind=EventHistoryKind.FIELD_CHANGED,
            occurred_at=NOW,
            actor_name="Coordinator Three",
            details=_field_change("registration_enabled", False, True),
        ),
        HistoryEntryAsShown(
            kind=EventHistoryKind.FIELD_CHANGED,
            occurred_at=NOW,
            actor_name="Coordinator Three",
            details=_field_change("registration_capacity", None, 100),
        ),
    ]


def test_changing_only_the_capacity_records_only_the_capacity(
    update: Update, confirmed_event_request: EventRequest, history_of: HistoryOf
) -> None:
    update(COORDINATOR_ID, ENABLE_WITH_100)

    update(COORDINATOR_ID, {"registration_capacity": 150})

    assert history_of(confirmed_event_request.id)[2:] == [
        (
            EventHistoryKind.FIELD_CHANGED,
            COORDINATOR_ID,
            _field_change("registration_capacity", 100, 150),
        )
    ]


def test_a_refused_change_writes_no_history(
    update: Update, confirmed_event_request: EventRequest, history_of: HistoryOf
) -> None:
    with pytest.raises(ValidationError):
        update(COORDINATOR_ID, {"registration_enabled": True})

    assert history_of(confirmed_event_request.id) == []


def test_now_defaults_to_the_current_instant(
    saved_users: list[User],
    confirmed_event_request: EventRequest,
    db_session: Session,
) -> None:
    before = datetime.now(timezone.utc)

    update_registration_settings(COORDINATOR_ID, REFERENCE, ENABLE_WITH_100, session=db_session)

    after = datetime.now(timezone.utc)
    entries = db_session.scalars(select(EventHistoryEntry)).all()
    assert len(entries) == 2
    for entry in entries:
        assert before <= entry.occurred_at <= after


def test_the_settings_and_their_history_are_saved_in_one_commit(
    mock_session: MagicMock, make_event_request: Callable[..., EventRequest]
) -> None:
    """At the only commit, the settings are set and the entries already added."""
    event_request = make_event_request(
        status=EventRequestStatus.CONFIRMED, coordinator_id=COORDINATOR_ID
    )
    # The event, then the number registered, which the capacity is checked against.
    mock_session.scalar.side_effect = [event_request, 0]
    seen_at_commit: list[tuple[bool, int | None, list[EventHistoryKind]]] = []

    def note_what_is_saved() -> None:
        added_kinds = [call.args[0].kind for call in mock_session.add.call_args_list]
        seen_at_commit.append(
            (event_request.registration_enabled, event_request.registration_capacity, added_kinds)
        )

    mock_session.commit.side_effect = note_what_is_saved

    update_registration_settings(
        COORDINATOR_ID, REFERENCE, ENABLE_WITH_100, session=mock_session, now=NOW
    )

    assert seen_at_commit == [(True, 100, [EventHistoryKind.FIELD_CHANGED] * 2)]


def test_a_call_that_changes_nothing_saves_nothing(
    mock_session: MagicMock, make_event_request: Callable[..., EventRequest]
) -> None:
    event_request = make_event_request(
        status=EventRequestStatus.CONFIRMED, coordinator_id=COORDINATOR_ID
    )
    event_request.registration_enabled = True
    event_request.registration_capacity = 100
    mock_session.scalar.side_effect = [event_request, 0]

    update_registration_settings(
        COORDINATOR_ID, REFERENCE, ENABLE_WITH_100, session=mock_session, now=NOW
    )

    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()
