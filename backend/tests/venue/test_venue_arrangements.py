"""Unit tests for SCRUM-93 — several venue arrangements for one event.

An arrangement is a ``VenueBookingRequest``. This file covers retiring one and the
"active arrangement" seam that SCRUM-75 counts to decide whether an event is
multi-venue (AC5, AC6).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError
from app.modules.events.models import EventHistoryEntry, EventHistoryKind, EventRequest
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue
from app.modules.venue.schemas import BookingRequestAsShown
from tests.venue.conftest import COORDINATOR_ID, SavedEvent, raise_booking

pytestmark = pytest.mark.scrum_93

SECOND_PERIOD = {
    "starts_at": "2026-11-01T13:00:00+08:00",
    "ends_at": "2026-11-01T16:00:00+08:00",
}


def _two_venues(make_venue: Callable[..., Venue], save: Callable[..., None]) -> tuple[Venue, Venue]:
    """Save an auditorium and a breakout room."""
    auditorium = make_venue(name="Auditorium")
    breakout = make_venue(name="Breakout room")
    save(auditorium)
    save(breakout)
    return auditorium, breakout


def _two_arrangements(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    event: EventRequest,
) -> tuple[int, int]:
    """Raise one arrangement at each of two venues, earlier period first; return ids."""
    auditorium, breakout = _two_venues(make_venue, save)
    first = raise_booking(auditorium, event, db_session)
    second = raise_booking(breakout, event, db_session, **SECOND_PERIOD)
    return first.id, second.id


def test_a_new_arrangement_is_active(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    raise_booking(venue, event, db_session)

    assert services.count_active_arrangements(event.id, session=db_session) == 1


def test_an_event_with_two_venues_has_two_active_arrangements(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """SCRUM-75 calls an event multi-venue when this count is more than one."""
    event = saved_event()
    _two_arrangements(db_session, make_venue, save, event)

    assert services.count_active_arrangements(event.id, session=db_session) == 2


def test_a_withdrawn_arrangement_stops_counting(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    event = saved_event()
    first_id, second_id = _two_arrangements(db_session, make_venue, save, event)
    withdrawn = db_session.get(services.VenueBookingRequest, first_id)
    assert withdrawn is not None
    withdrawn.status = BookingRequestStatus.WITHDRAWN
    db_session.commit()

    active = services.list_active_arrangements(event.id, session=db_session)

    assert [arrangement.id for arrangement in active] == [second_id]


def test_active_arrangements_are_listed_earliest_period_first(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """The later period is raised first, so id order and period order disagree."""
    event = saved_event()
    auditorium, breakout = _two_venues(make_venue, save)
    later = raise_booking(breakout, event, db_session, **SECOND_PERIOD)
    earlier = raise_booking(auditorium, event, db_session)

    active = services.list_active_arrangements(event.id, session=db_session)

    assert [arrangement.id for arrangement in active] == [earlier.id, later.id]


def test_another_events_arrangements_are_not_counted(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    mine = saved_event()
    theirs = saved_event()
    raise_booking(venue, theirs, db_session)

    assert services.count_active_arrangements(mine.id, session=db_session) == 0


def _history(session: Session) -> list[EventHistoryEntry]:
    return session.query(EventHistoryEntry).all()


def _withdraw(event: EventRequest, arrangement_id: int, session: Session) -> BookingRequestAsShown:
    return services.withdraw_arrangement(
        event.reference, arrangement_id, coordinator_id=COORDINATOR_ID, session=session
    )


def test_withdrawing_an_arrangement_marks_it_withdrawn(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)

    shown = _withdraw(event, arrangement.id, db_session)

    assert shown.request.status is BookingRequestStatus.WITHDRAWN
    assert services.count_active_arrangements(event.id, session=db_session) == 0


def test_withdrawing_one_arrangement_leaves_the_others_untouched(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """AC6's core promise for a multi-venue event."""
    event = saved_event()
    first_id, second_id = _two_arrangements(db_session, make_venue, save, event)

    _withdraw(event, first_id, db_session)

    survivor = db_session.get(services.VenueBookingRequest, second_id)
    assert survivor is not None
    assert survivor.status is BookingRequestStatus.PENDING
    assert [a.id for a in services.list_active_arrangements(event.id, session=db_session)] == [
        second_id
    ]


def test_withdrawing_writes_a_history_entry_naming_the_arrangement(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)

    _withdraw(event, arrangement.id, db_session)

    withdrawn = [
        entry
        for entry in _history(db_session)
        if entry.kind is EventHistoryKind.VENUE_ARRANGEMENT_WITHDRAWN
    ]
    assert len(withdrawn) == 1
    assert withdrawn[0].actor_id == COORDINATOR_ID
    assert withdrawn[0].details == {
        "venue_booking_request_id": arrangement.id,
        "venue_id": venue.id,
    }


def test_withdrawing_an_already_withdrawn_arrangement_is_refused(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """Review Focus 1: a second withdrawal must not pass silently."""
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)
    _withdraw(event, arrangement.id, db_session)

    with pytest.raises(ConflictError) as caught:
        _withdraw(event, arrangement.id, db_session)

    assert caught.value.message == (
        "Only a pending arrangement can be withdrawn; this one is withdrawn."
    )


def test_an_arrangement_belonging_to_another_event_is_not_found(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """Review Focus 2: ids must not cross between events."""
    mine = saved_event()
    theirs = saved_event()
    theirs_arrangement = raise_booking(venue, theirs, db_session)

    with pytest.raises(NotFoundError) as caught:
        _withdraw(mine, theirs_arrangement.id, db_session)

    assert caught.value.message == "Venue arrangement not found."


def test_an_unknown_arrangement_id_is_not_found(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    raise_booking(venue, event, db_session)

    with pytest.raises(NotFoundError):
        _withdraw(event, 9999, db_session)


def test_a_coordinator_who_is_not_assigned_cannot_withdraw(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)

    with pytest.raises(NotFoundError):
        services.withdraw_arrangement(
            event.reference, arrangement.id, coordinator_id=99, session=db_session
        )


def _cancel_all(event: EventRequest, session: Session) -> list[BookingRequestAsShown]:
    return services.cancel_all_arrangements(
        event.reference, coordinator_id=COORDINATOR_ID, session=session
    )


def test_cancelling_all_retires_every_arrangement(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    event = saved_event()
    _two_arrangements(db_session, make_venue, save, event)

    retired = _cancel_all(event, db_session)

    assert len(retired) == 2
    assert all(shown.request.status is BookingRequestStatus.WITHDRAWN for shown in retired)
    assert services.count_active_arrangements(event.id, session=db_session) == 0


def test_cancelling_all_leaves_another_events_arrangements_alone(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    mine = saved_event()
    theirs = saved_event()
    raise_booking(venue, mine, db_session)
    raise_booking(venue, theirs, db_session)

    _cancel_all(mine, db_session)

    assert services.count_active_arrangements(theirs.id, session=db_session) == 1


def test_cancelling_all_on_an_event_with_no_arrangements_does_nothing(
    db_session: Session, saved_event: SavedEvent
) -> None:
    """Review Focus 3: an empty event is not an error."""
    event = saved_event()

    assert _cancel_all(event, db_session) == []
    assert _history(db_session) == []


def test_cancelling_all_skips_arrangements_already_withdrawn(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """A second cancel-all must not refuse because the first already retired them."""
    event = saved_event()
    first_id, _ = _two_arrangements(db_session, make_venue, save, event)
    _withdraw(event, first_id, db_session)

    retired = _cancel_all(event, db_session)

    assert len(retired) == 1
    assert services.count_active_arrangements(event.id, session=db_session) == 0


def test_cancelling_all_for_an_event_that_is_not_the_callers_changes_nothing(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """A refused call writes nothing: every arrangement stays pending, no new history.

    Every active arrangement is pending, so the helper's 409 cannot fire part-way
    through the loop; the refusal that can happen is the 404 before the loop starts.
    """
    event = saved_event()
    _two_arrangements(db_session, make_venue, save, event)
    history_before = len(_history(db_session))

    with pytest.raises(NotFoundError):
        services.cancel_all_arrangements(event.reference, coordinator_id=99, session=db_session)

    active = services.list_active_arrangements(event.id, session=db_session)
    assert [arrangement.status for arrangement in active] == [BookingRequestStatus.PENDING] * 2
    assert len(_history(db_session)) == history_before
