"""Fixtures shared by the venue tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.clock import app_timezone, local_today
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.venue import services
from app.modules.venue.models import (
    Booking,
    BookingRequestStatus,
    BookingStatus,
    Venue,
    VenueBlock,
    VenueBookingRequest,
)
from app.modules.venue.schemas import BookingRequestAsShown

COORDINATOR_ID = 3
#: The Venue Staff user ``saved_users`` saves; they decide booking requests (SCRUM-43).
VENUE_STAFF_ID = 4
SavedEvent = Callable[..., EventRequest]
VenueWithBuffers = Callable[..., Venue]
SaveBooking = Callable[..., Booking]
SINGAPORE = timezone(timedelta(hours=8))
#: How far ahead the ``multi_venue_request`` fixture's event starts.
EVENT_DAYS_AWAY = 30


def at(hour: int, minute: int = 0, *, day: int = 1) -> datetime:
    """A moment on 1 November 2026 (or ``day``) in Singapore time."""
    return datetime(2026, 11, day, hour, minute, tzinfo=SINGAPORE)


def period(start: datetime, end: datetime) -> dict[str, str]:
    """The ``raise_booking`` overrides for a request from ``start`` to ``end``."""
    return {"starts_at": start.isoformat(), "ends_at": end.isoformat()}


def booking_payload(**overrides: Any) -> dict[str, Any]:
    """A valid payload for raising a request; ``overrides`` replace its fields."""
    payload = {
        "venue_id": 3,
        "starts_at": "2026-11-01T09:00:00+08:00",
        "ends_at": "2026-11-01T12:00:00+08:00",
        "purpose": "Main hall",
    }
    return {**payload, **overrides}


def raise_booking(
    venue: Venue, event: EventRequest, session: Session, **overrides: Any
) -> VenueBookingRequest:
    """Raise a booking request for ``event`` at ``venue`` as its coordinator."""
    payload = booking_payload(**{"venue_id": venue.id, **overrides})
    shown = services.raise_booking_request(
        event.reference, payload, requested_by=COORDINATOR_ID, session=session
    )
    return shown.request


def decide(
    request_id: int, outcome: str, session: Session, reason: str | None = None
) -> VenueBookingRequest:
    """Decide a request as Venue Staff; ``reason`` is left out when it is ``None``."""
    payload: dict[str, Any] = {"outcome": outcome}
    if reason is not None:
        payload["reason"] = reason
    shown = services.decide_booking_request(
        request_id, payload, decided_by=VENUE_STAFF_ID, session=session
    )
    return shown.request


def approve_safety(event: EventRequest, session: Session) -> None:
    """Record the Safety Officer approving the event, as the history holds it."""
    approval = EventHistoryEntry(
        event_request=event,
        kind=EventHistoryKind.SAFETY_OUTCOME_RECORDED,
        actor_id=None,
        details={"outcome": "approved"},
        occurred_at=datetime.now(UTC),
    )
    session.add(approval)
    session.commit()


def event_starts_at() -> datetime:
    """When ``multi_venue_event`` starts: 09:00, 30 days from today."""
    starts_on = local_today() + timedelta(days=EVENT_DAYS_AWAY)
    return datetime.combine(starts_on, time(9, 0), tzinfo=app_timezone())


def hours_from_now(hours: int) -> datetime:
    """A moment ``hours`` from now (negative: ago), for a live or a passed expiry."""
    return datetime.now(UTC) + timedelta(hours=hours)


def place_hold(request_id: int, expires_at: datetime, session: Session) -> VenueBookingRequest:
    """Place a hold on a request as Venue Staff; the expiry is sent as ISO 8601."""
    shown = services.place_booking_hold(
        request_id, {"expires_at": expires_at.isoformat()}, session=session
    )
    return shown.request


def change_expiry(request_id: int, expires_at: datetime, session: Session) -> VenueBookingRequest:
    """Change a hold's expiry as Venue Staff; the expiry is sent as ISO 8601."""
    shown = services.change_hold_expiry(
        request_id, {"expires_at": expires_at.isoformat()}, session=session
    )
    return shown.request


SECOND_PERIOD = {
    "starts_at": "2026-11-01T13:00:00+08:00",
    "ends_at": "2026-11-01T16:00:00+08:00",
}


def two_venues(make_venue: Callable[..., Venue], save: Callable[..., None]) -> tuple[Venue, Venue]:
    """Save an auditorium and a breakout room."""
    auditorium = make_venue(name="Auditorium")
    breakout = make_venue(name="Breakout room")
    save(auditorium)
    save(breakout)
    return auditorium, breakout


def two_arrangements(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    event: EventRequest,
) -> tuple[int, int]:
    """Raise one arrangement at each of two venues, earlier period first; return ids."""
    auditorium, breakout = two_venues(make_venue, save)
    first = raise_booking(auditorium, event, db_session)
    second = raise_booking(breakout, event, db_session, **SECOND_PERIOD)
    return first.id, second.id


def saved_requests(session: Session) -> list[VenueBookingRequest]:
    """Every booking request saved, to check what a call did or did not save."""
    return session.query(VenueBookingRequest).all()


@pytest.fixture()
def shown() -> BookingRequestAsShown:
    """A Pending request as Venue Staff see it, beside its event's details.

    For the route tests, which replace the services: the request is never saved.
    """
    request = VenueBookingRequest(
        event_id=5,
        venue_id=2,
        requested_by=COORDINATOR_ID,
        starts_at=datetime(2026, 11, 1, 1, 0, tzinfo=UTC),
        ends_at=datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        purpose="Main hall",
        expected_occupancy=80,
        required_layout=None,
        status=BookingRequestStatus.PENDING,
    )
    request.id = 11
    return BookingRequestAsShown(
        request=request,
        proposed_date=date(2026, 11, 1),
        end_date=date(2026, 11, 2),
        start_time=time(9, 0),
        end_time=time(17, 30),
        accessibility_needs="Step-free entrance",
    )


@pytest.fixture()
def reload_venue(db_session: Session) -> Callable[[int], Venue]:
    """Read a venue back from the database rather than from the session's cache."""

    def _reload(venue_id: int) -> Venue:
        db_session.expire_all()
        venue = db_session.get(Venue, venue_id)
        assert venue is not None
        return venue

    return _reload


@pytest.fixture()
def make_booking() -> Callable[..., Booking]:
    """Factory for bookings against a venue; add one to ``db_session`` to persist it."""

    def _make(
        venue: Venue,
        start: datetime,
        end: datetime,
        *,
        status: BookingStatus = BookingStatus.CONFIRMED,
        event_id: int | None = None,
        hold_expires_at: datetime | None = None,
    ) -> Booking:
        return Booking(
            venue_id=venue.id,
            start_time=start,
            end_time=end,
            status=status,
            event_id=event_id,
            hold_expires_at=hold_expires_at,
        )

    return _make


@pytest.fixture()
def make_block() -> Callable[..., VenueBlock]:
    """Factory for blocked periods; add one to ``db_session`` to persist it."""

    def _make(
        venue: Venue, start: datetime, end: datetime, *, reason: str = "Maintenance"
    ) -> VenueBlock:
        return VenueBlock(venue_id=venue.id, start_time=start, end_time=end, reason=reason)

    return _make


@pytest.fixture()
def saved_event(save: Callable[..., None]) -> Callable[..., EventRequest]:
    """Factory for a saved event: approved, coordinated by user 3, 80 attending.

    It runs on 1 November 2026 and the next day, from 09:00, unless ``proposed_date`` or
    ``start_time`` say otherwise; the end date always follows the proposed date.

    The event has no layout of its own, only free-text venue requirements.
    """
    counter = {"n": 0}

    def _save(
        status: EventRequestStatus = EventRequestStatus.APPROVED,
        *,
        proposed_date: date = date(2026, 11, 1),
        start_time: time = time(9, 0),
    ) -> EventRequest:
        counter["n"] += 1
        event = EventRequest(
            reference=f"EVR-{counter['n']:08d}",
            status=status,
            organiser_id=7,
            coordinator_id=COORDINATOR_ID,
            name="Partner Summit",
            proposed_date=proposed_date,
            end_date=proposed_date + timedelta(days=1),
            start_time=start_time,
            end_time=time(17, 30),
            expected_attendance=80,
            accessibility_needs="Step-free entrance",
            registration_required=False,
        )
        save(event)
        return event

    return _save


@pytest.fixture()
def venue_with_buffers(
    make_venue: Callable[..., Venue], save: Callable[..., None]
) -> VenueWithBuffers:
    """Save a venue with the given setup and turnaround minutes."""

    def _save(setup_minutes: int, turnaround_minutes: int) -> Venue:
        saved = make_venue(setup_minutes=setup_minutes, turnaround_minutes=turnaround_minutes)
        save(saved)
        return saved

    return _save


@pytest.fixture()
def confirmed_booking(
    make_booking: Callable[..., Booking], save: Callable[..., None]
) -> SaveBooking:
    """Save a booking at a venue; it is confirmed unless ``status`` says otherwise."""

    def _save(
        venue: Venue,
        start: datetime,
        end: datetime,
        *,
        status: BookingStatus = BookingStatus.CONFIRMED,
        event_id: int | None = None,
        hold_expires_at: datetime | None = None,
    ) -> Booking:
        booking = make_booking(
            venue, start, end, status=status, event_id=event_id, hold_expires_at=hold_expires_at
        )
        save(booking)
        return booking

    return _save


@pytest.fixture()
def tentative_hold(confirmed_booking: SaveBooking) -> SaveBooking:
    """Save a tentative hold at a venue; live unless ``hold_expires_at`` is past."""

    def _save(
        venue: Venue,
        start: datetime,
        end: datetime,
        *,
        hold_expires_at: datetime | None = None,
    ) -> Booking:
        expires_at = hold_expires_at if hold_expires_at is not None else hours_from_now(24)
        return confirmed_booking(
            venue, start, end, status=BookingStatus.TENTATIVE, hold_expires_at=expires_at
        )

    return _save


@pytest.fixture()
def multi_venue_event(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    saved_users: list[object],
) -> EventRequest:
    """An event with a Pending request at each of two venues, so it is multi-venue.

    The event starts 30 days from now (``event_starts_at``), so an expiry between now
    and then is valid.
    """
    event = saved_event(proposed_date=local_today() + timedelta(days=EVENT_DAYS_AWAY))
    two_arrangements(db_session, make_venue, save, event)
    return event


@pytest.fixture()
def multi_venue_request(
    db_session: Session, multi_venue_event: EventRequest
) -> VenueBookingRequest:
    """The multi-venue event's first request: 09:00-12:00 on 1 November 2026."""
    return services.list_active_arrangements(multi_venue_event.id, session=db_session)[0]
