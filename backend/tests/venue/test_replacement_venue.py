"""Unit tests for SCRUM-92 — replacing a venue that became unavailable.

AC6: the coordinator raises a replacement request linked to the flagged arrangement,
for an approved event or one in Safety Review (ADR-0053), at another venue and for the
flagged arrangement's own date and times, which can't be changed (Product Owner, 25 Oct,
ADR-0108). AC7: approving the replacement
releases the flagged arrangement and cancels its booking, or its hold if it was On Hold
(ADR-0100). AC10: if the event had passed
its safety check, approving the replacement withdraws that approval, and an event in
Safety Review goes back to Approved to be sent again. AC9, AC10 (Product Owner, 26 Oct):
when a replacement is approved for an event a venue sent back from Confirmed, the
Organiser who submitted it is told, naming the event, both venues and the category.

The services run against ``db_session``. The flagged arrangement is at the Auditorium,
09:00 to 12:00 on 1 November 2026; the replacement is at the Breakout room.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import services as event_services
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationSchema
from app.modules.notifications.services import NotificationKind
from app.modules.venue import services
from app.modules.venue.models import (
    BookingRequestStatus,
    BookingStatus,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import (
    COORDINATOR_ID,
    VENUE_STAFF_ID,
    SavedEvent,
    approve_safety,
    at,
    block,
    bookings,
    decide,
    history_entries,
    hours_from_now,
    place_hold,
    raise_booking,
    reload_event,
    reload_request,
    two_venues,
)

pytestmark = pytest.mark.scrum_92

NOT_FLAGGED_MESSAGE = "This venue arrangement does not need an alternative venue."
SAME_VENUE_MESSAGE = "A replacement must be at a different venue from the one it replaces."
#: The flagged arrangement's period, 09:00 to 12:00 on 1 November 2026 (business time).
LOCKED_PERIOD_MESSAGE = (
    "A replacement keeps the date and times of the booking it replaces:"
    " 2026-11-01 09:00 to 2026-11-01 12:00."
)
#: The ``saved_users`` organiser, of client organisation 3.
ORGANISER_ID = 7
#: What the organiser of an event sent back is told once its replacement is approved
#: (AC9): the event, both venues and the category of what flagged the original.
ORGANISER_TOLD = (
    "Auditorium became unavailable for Partner Summit ({category}), and Breakout room has"
    " been approved in its place. The event still needs Safety Review and confirmation."
)
#: AC6: the planning stage, and Safety Review, which a flag leaves an event in (AC3).
MAY_REPLACE = {EventRequestStatus.APPROVED, EventRequestStatus.SAFETY_REVIEW}
#: A draft is left out: a coordinator gets a 404 for it, not a 409 (ADR-0024).
MAY_NOT_REPLACE = [
    status
    for status in EventRequestStatus
    if status not in MAY_REPLACE and status is not EventRequestStatus.DRAFT
]


class Flagged:
    """An event whose Approved arrangement at the Auditorium a block has flagged."""

    def __init__(self, event: EventRequest, original: VenueBookingRequest, other: Venue) -> None:
        self.event = event
        self.original = original
        self.other = other


def _booked_at_the_auditorium(
    session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> Flagged:
    """An approved event booked at the Auditorium, not yet flagged."""
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    original = decide(raise_booking(auditorium, event, session).id, "approved", session)
    return Flagged(event, original, breakout)


def _block_the_auditorium(booked: Flagged, session: Session, **overrides: Any) -> None:
    """Block the original's venue for part of its period, flagging it (AC1)."""
    auditorium = session.get(Venue, booked.original.venue_id)
    assert auditorium is not None
    block(auditorium, at(10), at(11), session, **overrides)


@pytest.fixture()
def flagged(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> Flagged:
    booked = _booked_at_the_auditorium(db_session, make_venue, save, saved_event)
    _block_the_auditorium(booked, db_session)
    return booked


@pytest.fixture()
def sent_back(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> Flagged:
    """As ``flagged``, but the event was Confirmed, so the block sent it back (AC3)."""
    booked = _booked_at_the_auditorium(db_session, make_venue, save, saved_event)
    booked.event.status = EventRequestStatus.CONFIRMED
    db_session.commit()
    _block_the_auditorium(booked, db_session)
    return booked


def _replace(flagged: Flagged, session: Session, **overrides: Any) -> VenueBookingRequest:
    """Raise a request at the other venue replacing the flagged arrangement (AC6)."""
    return raise_booking(
        flagged.other,
        flagged.event,
        session,
        replaces_request_id=flagged.original.id,
        **overrides,
    )


def _lift_the_block(flagged: Flagged, session: Session) -> None:
    """Lift the block that flagged the original: its venue is available again (AC8)."""
    [venue_block] = services.list_venue_blocks(flagged.original.venue_id, session=session)
    services.remove_venue_block(flagged.original.venue_id, venue_block.id, session=session)


def _set_event_status(session: Session, event: EventRequest, status: EventRequestStatus) -> None:
    event.status = status
    session.commit()


def _replacement_notices(session: Session) -> list[tuple[int, int, str | None]]:
    """Every "replacement venue approved" notice, as (recipient, event id, detail)."""
    stmt = (
        select(Notification)
        .where(Notification.kind == NotificationKind.REPLACEMENT_VENUE_APPROVED)
        .order_by(Notification.id)
    )
    rows = []
    for notification in session.scalars(stmt):
        rows.append((notification.recipient_id, notification.event_request_id, notification.detail))
    return rows


# --------------------------------------------------------------------------
# AC6 — a replacement request linked to the flagged arrangement
# --------------------------------------------------------------------------


def test_a_replacement_is_raised_linked_to_the_flagged_arrangement(
    db_session: Session, flagged: Flagged
) -> None:
    replacement = _replace(flagged, db_session)

    saved = reload_request(db_session, replacement.id)
    assert saved.replaces_request_id == flagged.original.id
    assert saved.venue_id == flagged.other.id
    assert saved.status is BookingRequestStatus.PENDING


def test_raising_the_replacement_leaves_the_flagged_arrangement_as_it_was(
    db_session: Session, flagged: Flagged
) -> None:
    """The original stands until the replacement is approved (AC4, AC7)."""
    _replace(flagged, db_session)

    original = reload_request(db_session, flagged.original.id)
    assert original.status is BookingRequestStatus.APPROVED
    assert original.needs_alternative_venue is True


@pytest.mark.parametrize("status", sorted(MAY_REPLACE, key=lambda status: status.value))
def test_an_approved_event_or_one_in_safety_review_may_raise_a_replacement(
    db_session: Session, flagged: Flagged, status: EventRequestStatus
) -> None:
    _set_event_status(db_session, flagged.event, status)

    replacement = _replace(flagged, db_session)

    assert replacement.replaces_request_id == flagged.original.id


@pytest.mark.parametrize("status", MAY_NOT_REPLACE)
def test_an_event_at_any_other_status_may_not_raise_a_replacement(
    db_session: Session, flagged: Flagged, status: EventRequestStatus
) -> None:
    _set_event_status(db_session, flagged.event, status)

    with pytest.raises(ConflictError) as refusal:
        _replace(flagged, db_session)

    assert refusal.value.message == (
        "Only an approved event or one in Safety Review can replace a venue;"
        f" this one is {status.value}."
    )


def test_an_event_in_safety_review_still_may_not_raise_an_ordinary_request(
    db_session: Session, flagged: Flagged
) -> None:
    """Only a replacement gets past SCRUM-42's approved-only rule."""
    _set_event_status(db_session, flagged.event, EventRequestStatus.SAFETY_REVIEW)

    with pytest.raises(ConflictError):
        raise_booking(flagged.other, flagged.event, db_session)


def test_a_replacement_for_an_arrangement_that_is_not_flagged_is_refused(
    db_session: Session, venue: Venue, saved_event: SavedEvent, make_venue: Callable[..., Venue]
) -> None:
    event = saved_event()
    unflagged = raise_booking(venue, event, db_session)
    other = make_venue(name="Annex")
    db_session.add(other)
    db_session.commit()

    with pytest.raises(ValidationError) as refusal:
        raise_booking(other, event, db_session, replaces_request_id=unflagged.id)

    assert refusal.value.details == {"replaces_request_id": [NOT_FLAGGED_MESSAGE]}


@pytest.mark.parametrize(
    "period",
    [
        pytest.param({}, id="for the original period"),
        pytest.param(
            {"starts_at": at(13).isoformat(), "ends_at": at(16).isoformat()},
            id="at another time",
        ),
    ],
)
def test_a_replacement_at_the_venue_it_replaces_is_refused_on_venue_id(
    db_session: Session, flagged: Flagged, period: dict[str, str]
) -> None:
    """The Product Owner, 19 Oct: a replacement is always another venue (AC6, ADR-0100).

    For an arrangement that needs an alternative venue because its venue became
    unavailable; one flagged only after a change keeps the old rule (ADR-0100).

    The same venue at another time is a change to the event (SCRUM-56, SCRUM-57).
    """
    auditorium = db_session.get(Venue, flagged.original.venue_id)
    assert auditorium is not None
    before = db_session.scalars(select(VenueBookingRequest.id)).all()

    with pytest.raises(ValidationError) as refusal:
        raise_booking(
            auditorium,
            flagged.event,
            db_session,
            replaces_request_id=flagged.original.id,
            **period,
        )

    assert refusal.value.message == "Invalid request."
    assert refusal.value.details == {"venue_id": [SAME_VENUE_MESSAGE]}
    assert db_session.scalars(select(VenueBookingRequest.id)).all() == before


@pytest.mark.parametrize(
    ("period", "refused_fields"),
    [
        pytest.param({"starts_at": at(10).isoformat()}, ["starts_at"], id="a later start"),
        pytest.param({"ends_at": at(13).isoformat()}, ["ends_at"], id="a later end"),
        pytest.param(
            {"starts_at": at(9, day=2).isoformat(), "ends_at": at(12, day=2).isoformat()},
            ["starts_at", "ends_at"],
            id="the same times on another day",
        ),
    ],
)
def test_a_replacement_for_another_period_is_refused_on_the_time_fields(
    db_session: Session, flagged: Flagged, period: dict[str, str], refused_fields: list[str]
) -> None:
    """The Product Owner, 25 Oct: a replacement can't move the event (AC6)."""
    before = db_session.scalars(select(VenueBookingRequest.id)).all()

    with pytest.raises(ValidationError) as refusal:
        _replace(flagged, db_session, **period)

    assert refusal.value.message == "Invalid request."
    assert refusal.value.details == {field: [LOCKED_PERIOD_MESSAGE] for field in refused_fields}
    assert db_session.scalars(select(VenueBookingRequest.id)).all() == before


@pytest.mark.parametrize(
    "period",
    [
        pytest.param(
            {"starts_at": "2026-11-01T01:00:00Z", "ends_at": "2026-11-01T04:00:00Z"},
            id="in UTC",
        ),
        pytest.param(
            {"starts_at": "2026-11-01T09:00:00", "ends_at": "2026-11-01T12:00:00"},
            id="in business time with no offset",
        ),
    ],
)
def test_the_flagged_period_written_another_way_is_the_same_period(
    db_session: Session, flagged: Flagged, period: dict[str, str]
) -> None:
    """The times are compared as instants, as every period is (ADR-0009)."""
    replacement = _replace(flagged, db_session, **period)

    assert (replacement.starts_at, replacement.ends_at) == (
        flagged.original.starts_at,
        flagged.original.ends_at,
    )


def test_a_replacement_for_a_released_arrangement_is_refused(
    db_session: Session, flagged: Flagged
) -> None:
    """Released, it no longer needs anything, though its flags stay as the record."""
    flagged.original.status = BookingRequestStatus.RELEASED
    db_session.commit()

    with pytest.raises(ValidationError) as refusal:
        _replace(flagged, db_session)

    assert refusal.value.details == {"replaces_request_id": [NOT_FLAGGED_MESSAGE]}


def test_a_replacement_for_another_events_arrangement_is_refused_as_not_found(
    db_session: Session, flagged: Flagged, saved_event: SavedEvent
) -> None:
    """Another event's flagged arrangement, so only the event check can refuse it."""
    another_event = saved_event()

    with pytest.raises(ValidationError) as refusal:
        raise_booking(
            flagged.other, another_event, db_session, replaces_request_id=flagged.original.id
        )

    assert refusal.value.details == {"replaces_request_id": ["Venue arrangement not found."]}


def test_a_replacement_for_an_unknown_arrangement_is_refused_as_not_found(
    db_session: Session, flagged: Flagged
) -> None:
    with pytest.raises(ValidationError) as refusal:
        raise_booking(flagged.other, flagged.event, db_session, replaces_request_id=999)

    assert refusal.value.details == {"replaces_request_id": ["Venue arrangement not found."]}


def test_a_refused_replacement_saves_nothing(db_session: Session, flagged: Flagged) -> None:
    before = db_session.scalars(select(VenueBookingRequest.id)).all()

    with pytest.raises(ValidationError):
        raise_booking(flagged.other, flagged.event, db_session, replaces_request_id=999)

    assert db_session.scalars(select(VenueBookingRequest.id)).all() == before


def _replace_naming(flagged: Flagged, session: Session, replaces: Any) -> None:
    """Raise a replacement whose ``replaces_request_id`` is ``replaces`` as sent."""
    raise_booking(flagged.other, flagged.event, session, replaces_request_id=replaces)


@pytest.mark.parametrize(
    "as_sent",
    [
        pytest.param(lambda original_id: original_id + 0.5, id="a fraction"),
        pytest.param(str, id="a numeric string"),
        pytest.param(lambda _: True, id="true"),
    ],
)
def test_a_replacement_id_that_is_not_a_whole_number_is_refused(
    db_session: Session, flagged: Flagged, as_sent: Callable[[int], Any]
) -> None:
    """The original's id sent as ``1.5`` or ``"1"`` used to load as 1 and replace it."""
    with pytest.raises(ValidationError) as refusal:
        _replace_naming(flagged, db_session, as_sent(flagged.original.id))

    assert refusal.value.details == {"replaces_request_id": ["Not a valid integer."]}


def test_a_replacement_id_below_one_is_refused(db_session: Session, flagged: Flagged) -> None:
    with pytest.raises(ValidationError) as refusal:
        _replace_naming(flagged, db_session, 0)

    assert refusal.value.details == {
        "replaces_request_id": ["replaces_request_id must be a positive number."]
    }


# --------------------------------------------------------------------------
# AC7 — approving the replacement releases the flagged arrangement
# --------------------------------------------------------------------------


def test_approving_the_replacement_releases_the_flagged_arrangement_and_its_booking(
    db_session: Session, flagged: Flagged
) -> None:
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    released = reload_request(db_session, flagged.original.id)
    assert released.status is BookingRequestStatus.RELEASED
    assert released.needs_alternative_venue is False
    assert len(released.flags) == 1
    assert bookings(db_session) == [
        (flagged.original.venue_id, BookingStatus.CANCELLED),
        (flagged.other.id, BookingStatus.CONFIRMED),
    ]


def test_the_decisions_history_entry_names_the_arrangement_it_replaced(
    db_session: Session, flagged: Flagged
) -> None:
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    approved_entry = [
        entry
        for entry in db_session.scalars(select(EventHistoryEntry))
        if entry.kind is EventHistoryKind.VENUE_BOOKING_APPROVED
        and entry.details["venue_booking_request_id"] == replacement.id
    ]
    assert approved_entry[0].details["replaces_request_id"] == flagged.original.id


def test_rejecting_the_replacement_leaves_the_flagged_arrangement_standing(
    db_session: Session, flagged: Flagged
) -> None:
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "rejected", db_session, reason="Booked out.")

    original = reload_request(db_session, flagged.original.id)
    assert original.status is BookingRequestStatus.APPROVED
    assert original.needs_alternative_venue is True
    assert bookings(db_session) == [(flagged.original.venue_id, BookingStatus.CONFIRMED)]


def test_approving_an_ordinary_request_releases_nothing(
    db_session: Session, flagged: Flagged
) -> None:
    """A second venue for the event, not a replacement: the flagged one stays."""
    ordinary = raise_booking(flagged.other, flagged.event, db_session)

    decide(ordinary.id, "approved", db_session)

    assert reload_request(db_session, flagged.original.id).status is BookingRequestStatus.APPROVED
    assert bookings(db_session) == [
        (flagged.original.venue_id, BookingStatus.CONFIRMED),
        (flagged.other.id, BookingStatus.CONFIRMED),
    ]


def test_a_flagged_pending_request_is_released_with_no_booking_to_cancel(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    pending = raise_booking(auditorium, event, db_session)
    block(auditorium, at(10), at(11), db_session)
    replacement = raise_booking(breakout, event, db_session, replaces_request_id=pending.id)

    decide(replacement.id, "approved", db_session)

    assert reload_request(db_session, pending.id).status is BookingRequestStatus.RELEASED
    assert bookings(db_session) == [(breakout.id, BookingStatus.CONFIRMED)]


def test_a_flagged_request_on_hold_is_released_and_its_hold_cancelled(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
) -> None:
    """AC7: if the flagged booking was On Hold, its hold is released (ADR-0100)."""
    held = place_hold(multi_venue_request.id, hours_from_now(24), db_session)
    held_venue = db_session.get(Venue, held.venue_id)
    assert held_venue is not None
    block(held_venue, at(10), at(11), db_session)
    annex = make_venue(name="Annex")
    save(annex)
    event = reload_event(db_session, held.event_id)
    replacement = raise_booking(annex, event, db_session, replaces_request_id=held.id)

    decide(replacement.id, "approved", db_session)

    released = reload_request(db_session, held.id)
    assert released.status is BookingRequestStatus.RELEASED
    assert released.needs_alternative_venue is False
    assert released.booking is not None
    assert released.booking.status is BookingStatus.CANCELLED


def test_only_the_replaced_arrangements_booking_is_cancelled(
    db_session: Session, flagged: Flagged
) -> None:
    """A later booking at the same venue for the same event is another arrangement."""
    auditorium = db_session.get(Venue, flagged.original.venue_id)
    assert auditorium is not None
    later = raise_booking(
        auditorium,
        flagged.event,
        db_session,
        starts_at=at(13).isoformat(),
        ends_at=at(16).isoformat(),
    )
    decide(later.id, "approved", db_session)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    assert bookings(db_session) == [
        (flagged.original.venue_id, BookingStatus.CANCELLED),
        (flagged.original.venue_id, BookingStatus.CONFIRMED),
        (flagged.other.id, BookingStatus.CONFIRMED),
    ]


def test_a_replacement_approved_after_the_flag_cleared_still_releases_the_original(
    db_session: Session, flagged: Flagged
) -> None:
    """ADR-0053 default, pending the customer: the coordinator asked to replace it.

    To keep the original once its venue is free again, they withdraw the replacement.
    """
    replacement = _replace(flagged, db_session)
    _lift_the_block(flagged, db_session)
    assert reload_request(db_session, flagged.original.id).needs_alternative_venue is False

    decide(replacement.id, "approved", db_session)

    assert reload_request(db_session, flagged.original.id).status is BookingRequestStatus.RELEASED


def test_a_second_replacement_leaves_an_already_released_arrangement_released(
    db_session: Session, flagged: Flagged, make_venue: Callable[..., Venue]
) -> None:
    first = _replace(flagged, db_session)
    annex = make_venue(name="Annex")
    db_session.add(annex)
    db_session.commit()
    second = raise_booking(
        annex, flagged.event, db_session, replaces_request_id=flagged.original.id
    )
    decide(first.id, "approved", db_session)

    decide(second.id, "approved", db_session)

    assert reload_request(db_session, flagged.original.id).status is BookingRequestStatus.RELEASED
    assert [status for _, status in bookings(db_session)] == [
        BookingStatus.CANCELLED,
        BookingStatus.CONFIRMED,
        BookingStatus.CONFIRMED,
    ]


def _withdraw(event: EventRequest, request_id: int, session: Session) -> None:
    services.withdraw_arrangement(
        event.reference, request_id, coordinator_id=COORDINATOR_ID, session=session
    )


def _reject(event: EventRequest, request_id: int, session: Session) -> None:
    decide(request_id, "rejected", session, reason="Venue closed.")


@pytest.mark.parametrize(
    ("stop_holding", "left_as"),
    [
        pytest.param(_withdraw, BookingRequestStatus.WITHDRAWN, id="withdrawn"),
        pytest.param(_reject, BookingRequestStatus.REJECTED, id="rejected"),
    ],
)
def test_an_original_that_stopped_holding_its_venue_is_left_as_it_is(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    stop_holding: Callable[[EventRequest, int, Session], None],
    left_as: BookingRequestStatus,
) -> None:
    """ADR-0053 §11: an original already retired or decided against isn't released.

    The flagged Pending original is withdrawn or rejected after its replacement was
    raised; approving the replacement leaves that status as it is.
    """
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    pending = raise_booking(auditorium, event, db_session)
    block(auditorium, at(10), at(11), db_session)
    replacement = raise_booking(breakout, event, db_session, replaces_request_id=pending.id)
    stop_holding(event, pending.id, db_session)

    decide(replacement.id, "approved", db_session)

    assert reload_request(db_session, pending.id).status is left_as


def test_another_venue_booked_for_the_same_period_is_not_cancelled(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """Only the original's own booking is cancelled (AC7).

    The event also has the Breakout room for the same period, booked first, so a search
    that ignored the venue would cancel that booking instead of the original's.
    """
    auditorium, breakout = two_venues(make_venue, save)
    annex = make_venue(name="Annex")
    save(annex)
    event = saved_event()
    decide(raise_booking(breakout, event, db_session).id, "approved", db_session)
    original = decide(raise_booking(auditorium, event, db_session).id, "approved", db_session)
    block(auditorium, at(10), at(11), db_session)
    replacement = raise_booking(annex, event, db_session, replaces_request_id=original.id)

    decide(replacement.id, "approved", db_session)

    assert bookings(db_session) == [
        (breakout.id, BookingStatus.CONFIRMED),
        (auditorium.id, BookingStatus.CANCELLED),
        (annex.id, BookingStatus.CONFIRMED),
    ]


# --------------------------------------------------------------------------
# AC9, AC10 — the organiser of an event sent back hears of the approved replacement
# --------------------------------------------------------------------------


def test_the_organiser_of_an_event_sent_back_is_told_its_replacement_was_approved(
    db_session: Session, sent_back: Flagged
) -> None:
    """The Product Owner, 26 Oct: told how it resolves; only the submitter (AC10)."""
    replacement = _replace(sent_back, db_session)

    decide(replacement.id, "approved", db_session)

    assert _replacement_notices(db_session) == [
        (ORGANISER_ID, sent_back.event.id, ORGANISER_TOLD.format(category="maintenance"))
    ]
    [notice] = db_session.scalars(
        select(Notification).where(Notification.kind == NotificationKind.REPLACEMENT_VENUE_APPROVED)
    )
    shown = NotificationSchema().dump(notice)
    assert shown["message"] == "A replacement venue was approved for your event."
    assert shown["link"] == f"/events/{sent_back.event.reference}"


def test_the_notice_names_each_category_that_flagged_the_original_once(
    db_session: Session, sent_back: Flagged
) -> None:
    """Two more blocks over it, one of the same category: each is named once."""
    _block_the_auditorium(sent_back, db_session)
    _block_the_auditorium(sent_back, db_session, category="safety_concern", reason="Wiring.")
    replacement = _replace(sent_back, db_session)

    decide(replacement.id, "approved", db_session)

    assert _replacement_notices(db_session) == [
        (
            ORGANISER_ID,
            sent_back.event.id,
            ORGANISER_TOLD.format(category="maintenance, safety concern"),
        )
    ]


def test_a_replacement_approved_after_the_venue_is_available_again_still_tells_the_organiser(
    db_session: Session, sent_back: Flagged
) -> None:
    """The original is released, so the organiser hears of it (AC9, ADR-0111).

    The block is lifted while the replacement waits, so the organiser was told the
    original stands; approving the replacement then moves the event to the Breakout
    room. Lifting the block deleted the flags, so the category comes from the history.
    """
    replacement = _replace(sent_back, db_session)
    _lift_the_block(sent_back, db_session)

    decide(replacement.id, "approved", db_session)

    assert _replacement_notices(db_session) == [
        (ORGANISER_ID, sent_back.event.id, ORGANISER_TOLD.format(category="maintenance"))
    ]


def test_the_notice_names_only_what_flagged_the_replaced_arrangement(
    db_session: Session,
    sent_back: Flagged,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
) -> None:
    """Another of the event's venues, blocked for a safety concern, isn't named."""
    annex = make_venue(name="Annex")
    save(annex)
    decide(raise_booking(annex, sent_back.event, db_session).id, "approved", db_session)
    block(annex, at(10), at(11), db_session, category="safety_concern", reason="Wiring.")
    replacement = _replace(sent_back, db_session)

    decide(replacement.id, "approved", db_session)

    assert _replacement_notices(db_session) == [
        (ORGANISER_ID, sent_back.event.id, ORGANISER_TOLD.format(category="maintenance"))
    ]


def test_the_organiser_of_an_event_the_venue_did_not_send_back_is_not_told(
    db_session: Session, flagged: Flagged
) -> None:
    """The event was Approved when the block came, so it never went back (AC3, AC9)."""
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    assert _replacement_notices(db_session) == []


def test_a_rejected_replacement_tells_the_organiser_nothing(
    db_session: Session, sent_back: Flagged
) -> None:
    replacement = _replace(sent_back, db_session)

    decide(replacement.id, "rejected", db_session, reason="Booked out.")

    assert _replacement_notices(db_session) == []


def test_approving_an_ordinary_request_tells_the_organiser_nothing(
    db_session: Session, sent_back: Flagged
) -> None:
    """A second venue for the event replaces nothing (AC9 is about AC7)."""
    request = raise_booking(sent_back.other, sent_back.event, db_session)

    decide(request.id, "approved", db_session)

    assert _replacement_notices(db_session) == []


# --------------------------------------------------------------------------
# AC10 — a replacement withdraws the safety approval
# --------------------------------------------------------------------------


def test_a_replacement_withdraws_the_safety_approval_and_sends_the_event_back_to_approved(
    db_session: Session, flagged: Flagged
) -> None:
    _set_event_status(db_session, flagged.event, EventRequestStatus.SAFETY_REVIEW)
    approve_safety(flagged.event, db_session)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    assert event_services.has_safety_approval(flagged.event.id, session=db_session) is False
    assert reload_event(db_session, flagged.event.id).status is EventRequestStatus.APPROVED
    withdrawn = [
        entry
        for entry in db_session.scalars(select(EventHistoryEntry))
        if entry.kind is EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN
    ]
    assert [(entry.actor_id, entry.details) for entry in withdrawn] == [
        (
            VENUE_STAFF_ID,
            {
                "venue_booking_request_id": replacement.id,
                "replaces_request_id": flagged.original.id,
            },
        )
    ]


def test_a_returned_event_with_a_safety_approval_loses_it_and_stays_approved(
    db_session: Session, flagged: Flagged
) -> None:
    """Flagged while Confirmed, it went back to Approved (AC3) with its approval."""
    approve_safety(flagged.event, db_session)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    assert event_services.has_safety_approval(flagged.event.id, session=db_session) is False
    assert reload_event(db_session, flagged.event.id).status is EventRequestStatus.APPROVED


def test_an_event_without_a_safety_approval_has_nothing_withdrawn(
    db_session: Session, flagged: Flagged
) -> None:
    _set_event_status(db_session, flagged.event, EventRequestStatus.SAFETY_REVIEW)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    kinds = [entry.kind for entry in history_entries(db_session, flagged.event.id)]
    assert EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN not in kinds
    db_session.expire_all()
    assert db_session.get(EventRequest, flagged.event.id).status is EventRequestStatus.SAFETY_REVIEW


def test_approving_an_ordinary_request_keeps_the_safety_approval(
    db_session: Session, flagged: Flagged
) -> None:
    approve_safety(flagged.event, db_session)
    ordinary = raise_booking(flagged.other, flagged.event, db_session)

    decide(ordinary.id, "approved", db_session)

    assert event_services.has_safety_approval(flagged.event.id, session=db_session) is True


def test_a_rejected_replacement_keeps_the_safety_approval(
    db_session: Session, flagged: Flagged
) -> None:
    approve_safety(flagged.event, db_session)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "rejected", db_session, reason="Booked out.")

    assert event_services.has_safety_approval(flagged.event.id, session=db_session) is True


def _history_kinds(
    session: Session, event: EventRequest, viewer_id: int, viewer_role: Role
) -> list[EventHistoryKind]:
    entries = event_services.list_event_history(
        viewer_id, event.reference, viewer_role=viewer_role, session=session
    )
    return [entry.kind for entry in entries]


def test_the_withdrawal_is_shown_to_the_coordinator_and_the_organiser(
    db_session: Session, flagged: Flagged, saved_users: list[User]
) -> None:
    """Nothing on the record is hidden from the organiser (SCRUM-24 AC10, ADR-0104)."""
    flagged.event.organisation_id = 3
    approve_safety(flagged.event, db_session)
    decide(_replace(flagged, db_session).id, "approved", db_session)

    withdrawn = EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN
    organiser_sees = _history_kinds(db_session, flagged.event, ORGANISER_ID, Role.EVENT_ORGANISER)
    coordinator_sees = _history_kinds(
        db_session, flagged.event, COORDINATOR_ID, Role.EVENT_COORDINATOR
    )
    assert withdrawn in organiser_sees
    assert withdrawn in coordinator_sees


def test_the_event_can_pass_a_new_safety_check_after_the_withdrawal(
    db_session: Session, flagged: Flagged
) -> None:
    _set_event_status(db_session, flagged.event, EventRequestStatus.SAFETY_REVIEW)
    approve_safety(flagged.event, db_session)
    decide(_replace(flagged, db_session).id, "approved", db_session)

    sent = event_services.submit_for_safety_review(
        COORDINATOR_ID, flagged.event.reference, session=db_session
    )

    assert sent.status is EventRequestStatus.SAFETY_REVIEW
    latest = history_entries(db_session, flagged.event.id)[-1]
    assert latest.kind is EventHistoryKind.SAFETY_REVIEW_REQUESTED


# --------------------------------------------------------------------------
# AC13 (the last criterion) — approving a replacement doesn't re-check registration
# --------------------------------------------------------------------------


def test_a_replacement_smaller_than_the_registration_capacity_is_approved_as_it_stands(
    db_session: Session, flagged: Flagged
) -> None:
    """Registration capacity is the organiser's call, not the venue's (SCRUM-69).

    The event takes 500 registrations and the Breakout room holds 100, yet the
    replacement is approved and the capacity is left as the organiser set it.
    """
    flagged.event.registration_enabled = True
    flagged.event.registration_capacity = 500
    db_session.commit()
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    assert reload_request(db_session, replacement.id).status is BookingRequestStatus.APPROVED
    assert reload_event(db_session, flagged.event.id).registration_capacity == 500
