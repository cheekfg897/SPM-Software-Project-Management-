"""Unit tests for SCRUM-55: who has registered for an event, for the people running it.

``list_registrants`` answers an Event Organiser of the event's client organisation (AC1)
and the event's assigned Event Coordinator (AC2) with each registrant's name, email,
registration date and status (AC3), and the registered count against the capacity (AC4).
Anyone else gets the same 404 as an unknown reference (ADR-0012). An Attendee never
reaches the service: the route refuses their role with a 403
(``test_registrant_list_route.py``, AC5).

Runs against ``db_session``, so the filters and the order are really exercised.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.services import Registrant, RegistrantList, list_registrants

pytestmark = pytest.mark.scrum_55

MakeOpenEvent = Callable[..., EventRequest]
MakeRegistration = Callable[..., Registration]
MakeAttendee = Callable[..., User]
ListRegistrants = Callable[..., RegistrantList]

#: ``saved_users`` gives organiser 7 (organisation 3) and coordinators 3 and 9; every
#: event ``make_open_event`` saves is organiser 7's and assigned to coordinator 3.
ORGANISER = 7
#: Organiser 7's colleague in organisation 3, who wrote none of the events.
COLLEAGUE_ORGANISER = 11
OTHER_ORGANISATION_ORGANISER = 8
COORDINATOR = 3
OTHER_COORDINATOR = 9

NOT_FOUND_MESSAGE = "Event request not found."


@pytest.fixture(autouse=True)
def _staff(
    saved_users: list[User], make_user: Callable[..., User], save: Callable[..., None]
) -> None:
    """The people running the events, a colleague, and an organiser elsewhere."""
    save(
        make_user(
            email="organiser11@example.com",
            role=Role.EVENT_ORGANISER,
            organisation_id=3,
            user_id=COLLEAGUE_ORGANISER,
        ),
        make_user(
            email="organiser8@example.com",
            role=Role.EVENT_ORGANISER,
            organisation_id=4,
            user_id=OTHER_ORGANISATION_ORGANISER,
        ),
    )


@pytest.fixture()
def make_attendee(make_user: Callable[..., User], save: Callable[..., None]) -> MakeAttendee:
    """Factory for saved Attendees with their own name and email."""

    def _make(user_id: int, full_name: str) -> User:
        email = f"{full_name.split()[0].lower()}@example.com"
        attendee = make_user(email=email, full_name=full_name, role=Role.ATTENDEE, user_id=user_id)
        save(attendee)
        return attendee

    return _make


@pytest.fixture()
def registrants(db_session: Session) -> ListRegistrants:
    """The list ``viewer_id`` (with ``role``) sees for the event ``reference``."""

    def _list(viewer_id: int, role: Role, reference: str) -> RegistrantList:
        return list_registrants(viewer_id, reference, viewer_role=role, session=db_session)

    return _list


# --------------------------------------------------------------------------
# AC1, AC2 — only the people responsible for the event
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "organiser_id", [ORGANISER, COLLEAGUE_ORGANISER], ids=["who-submitted-it", "a-colleague"]
)
def test_an_organiser_of_the_events_organisation_sees_its_registrants(
    registrants: ListRegistrants,
    open_event: EventRequest,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
    organiser_id: int,
) -> None:
    make_registration(open_event, make_attendee(21, "Alice Tan").id)

    listing = registrants(organiser_id, Role.EVENT_ORGANISER, open_event.reference)

    assert [row.name for row in listing.items] == ["Alice Tan"]


def test_a_colleagues_draft_is_not_found(
    registrants: ListRegistrants, make_open_event: MakeOpenEvent
) -> None:
    """A draft is its author's alone, even within the organisation (ADR-0024)."""
    draft = make_open_event(status=EventRequestStatus.DRAFT)

    with pytest.raises(NotFoundError) as exc_info:
        registrants(COLLEAGUE_ORGANISER, Role.EVENT_ORGANISER, draft.reference)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == NOT_FOUND_MESSAGE


def test_an_organiser_of_another_organisation_is_refused(
    registrants: ListRegistrants,
    open_event: EventRequest,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
) -> None:
    make_registration(open_event, make_attendee(21, "Alice Tan").id)

    with pytest.raises(NotFoundError) as exc_info:
        registrants(OTHER_ORGANISATION_ORGANISER, Role.EVENT_ORGANISER, open_event.reference)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == NOT_FOUND_MESSAGE


def test_the_assigned_coordinator_sees_the_registrants(
    registrants: ListRegistrants,
    open_event: EventRequest,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
) -> None:
    make_registration(open_event, make_attendee(21, "Alice Tan").id)

    listing = registrants(COORDINATOR, Role.EVENT_COORDINATOR, open_event.reference)

    assert [row.name for row in listing.items] == ["Alice Tan"]


def test_a_coordinator_the_event_is_not_assigned_to_is_refused(
    registrants: ListRegistrants,
    open_event: EventRequest,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
) -> None:
    make_registration(open_event, make_attendee(21, "Alice Tan").id)

    with pytest.raises(NotFoundError) as exc_info:
        registrants(OTHER_COORDINATOR, Role.EVENT_COORDINATOR, open_event.reference)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == NOT_FOUND_MESSAGE


def test_an_unknown_reference_is_a_404(registrants: ListRegistrants) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        registrants(ORGANISER, Role.EVENT_ORGANISER, "EVR-NOSUCHEV")

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == NOT_FOUND_MESSAGE


# --------------------------------------------------------------------------
# AC3 — name, email, registration date and status, oldest registration first
# --------------------------------------------------------------------------


def test_each_registrant_shows_name_email_date_and_status_oldest_first(
    registrants: ListRegistrants,
    open_event: EventRequest,
    now: datetime,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
) -> None:
    carol = make_attendee(23, "Carol Lim")
    alice = make_attendee(21, "Alice Tan")
    bob = make_attendee(22, "Bob Ong")
    make_registration(open_event, carol.id, registered_at=now - timedelta(hours=1))
    make_registration(open_event, alice.id, registered_at=now - timedelta(days=2))
    make_registration(open_event, bob.id, registered_at=now)

    listing = registrants(ORGANISER, Role.EVENT_ORGANISER, open_event.reference)

    assert listing.items == [
        Registrant(
            name="Alice Tan",
            email="alice@example.com",
            registered_at=now - timedelta(days=2),
            status=RegistrationStatus.REGISTERED,
        ),
        Registrant(
            name="Carol Lim",
            email="carol@example.com",
            registered_at=now - timedelta(hours=1),
            status=RegistrationStatus.REGISTERED,
        ),
        Registrant(
            name="Bob Ong",
            email="bob@example.com",
            registered_at=now,
            status=RegistrationStatus.REGISTERED,
        ),
    ]


def test_registrations_made_at_the_same_moment_are_listed_in_the_order_saved(
    registrants: ListRegistrants,
    open_event: EventRequest,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
) -> None:
    """Saved Bob before Alice, so an alphabetical or reversed tie-break shows."""
    make_registration(open_event, make_attendee(22, "Bob Ong").id)
    make_registration(open_event, make_attendee(21, "Alice Tan").id)

    listing = registrants(ORGANISER, Role.EVENT_ORGANISER, open_event.reference)

    assert [row.name for row in listing.items] == ["Bob Ong", "Alice Tan"]


def test_another_events_registrations_are_not_included(
    registrants: ListRegistrants,
    make_open_event: MakeOpenEvent,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
) -> None:
    mine = make_open_event(name="Mine")
    decoy = make_open_event(name="Decoy")
    make_registration(mine, make_attendee(21, "Alice Tan").id)
    make_registration(decoy, make_attendee(22, "Bob Ong").id)
    make_registration(decoy, make_attendee(23, "Carol Lim").id)

    listing = registrants(ORGANISER, Role.EVENT_ORGANISER, mine.reference)

    assert [row.name for row in listing.items] == ["Alice Tan"]
    assert listing.registered_count == 1


# --------------------------------------------------------------------------
# AC4 — the registration count against the capacity
# --------------------------------------------------------------------------


def test_the_count_is_shown_against_the_capacity(
    registrants: ListRegistrants,
    make_open_event: MakeOpenEvent,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
) -> None:
    event = make_open_event(capacity=5)
    make_registration(event, make_attendee(21, "Alice Tan").id)
    make_registration(event, make_attendee(22, "Bob Ong").id)

    listing = registrants(ORGANISER, Role.EVENT_ORGANISER, event.reference)

    assert (listing.capacity, listing.registered_count, listing.places_left) == (5, 2, 3)


def test_a_full_event_has_no_places_left(
    registrants: ListRegistrants,
    make_open_event: MakeOpenEvent,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
) -> None:
    event = make_open_event(capacity=2)
    make_registration(event, make_attendee(21, "Alice Tan").id)
    make_registration(event, make_attendee(22, "Bob Ong").id)

    listing = registrants(ORGANISER, Role.EVENT_ORGANISER, event.reference)

    assert (listing.capacity, listing.registered_count, listing.places_left) == (2, 2, 0)


def test_places_left_never_goes_below_zero(
    registrants: ListRegistrants,
    make_open_event: MakeOpenEvent,
    make_attendee: MakeAttendee,
    make_registration: MakeRegistration,
) -> None:
    """A third registration at capacity 2 is only possible straight in the table."""
    event = make_open_event(capacity=2)
    for user_id, name in [(21, "Alice Tan"), (22, "Bob Ong"), (23, "Carol Lim")]:
        make_registration(event, make_attendee(user_id, name).id)

    listing = registrants(ORGANISER, Role.EVENT_ORGANISER, event.reference)

    assert (listing.capacity, listing.registered_count, listing.places_left) == (2, 3, 0)


def test_an_event_that_never_had_a_capacity_shows_none_and_no_places_left_figure(
    registrants: ListRegistrants, make_open_event: MakeOpenEvent, save: Callable[..., None]
) -> None:
    event = make_open_event()
    event.registration_enabled = False
    event.registration_capacity = None
    save(event)

    listing = registrants(ORGANISER, Role.EVENT_ORGANISER, event.reference)

    assert listing == RegistrantList(capacity=None, registered_count=0, places_left=None, items=[])
