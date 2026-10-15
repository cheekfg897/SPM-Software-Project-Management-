"""Unit tests for SCRUM-93 AC6 — changing one of an event's venue arrangements.

Only a pending arrangement changes, and only its purpose, occupancy, layout and
justification: the venue and period are the slot Venue Staff were asked about, so moving
either means withdrawing this arrangement and raising another.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.events.models import EventHistoryEntry, EventHistoryKind, EventRequest
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue
from app.modules.venue.schemas import BookingRequestAsShown
from tests.venue.conftest import COORDINATOR_ID, SavedEvent, raise_booking, two_arrangements

pytestmark = pytest.mark.scrum_93

UNSUITABLE_MESSAGE = "A justification is required because the venue is not suitable."
THIRD_PERIOD = {
    "starts_at": "2026-11-01T10:00:00+08:00",
    "ends_at": "2026-11-01T11:00:00+08:00",
}


def _change(
    event: EventRequest, arrangement_id: int, session: Session, **fields: Any
) -> BookingRequestAsShown:
    return services.change_arrangement(
        event.reference,
        arrangement_id,
        dict(fields),
        coordinator_id=COORDINATOR_ID,
        session=session,
    )


def _changed_entries(session: Session) -> list[EventHistoryEntry]:
    return [
        entry
        for entry in session.query(EventHistoryEntry).all()
        if entry.kind is EventHistoryKind.VENUE_ARRANGEMENT_CHANGED
    ]


def _snapshots(session: Session, arrangement_ids: list[int]) -> dict[int, tuple[Any, ...]]:
    """What each arrangement currently says, to compare before and after a change."""
    snapshots = {}
    for arrangement_id in arrangement_ids:
        arrangement = session.get(services.VenueBookingRequest, arrangement_id)
        assert arrangement is not None
        snapshots[arrangement_id] = (
            arrangement.purpose,
            arrangement.expected_occupancy,
            arrangement.required_layout,
            arrangement.status,
        )
    return snapshots


def test_changing_the_purpose_keeps_everything_else(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)
    occupancy_before = arrangement.expected_occupancy

    shown = _change(event, arrangement.id, db_session, purpose="Breakout session")

    assert shown.request.purpose == "Breakout session"
    assert shown.request.expected_occupancy == occupancy_before
    assert shown.request.status is BookingRequestStatus.PENDING


def test_changing_one_of_three_arrangements_leaves_the_other_two_untouched(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    venue: Venue,
    saved_event: SavedEvent,
) -> None:
    """AC6's core promise for a multi-venue event."""
    event = saved_event()
    changed_id, second_id = two_arrangements(db_session, make_venue, save, event)
    third_id = raise_booking(venue, event, db_session, **THIRD_PERIOD).id
    others_before = _snapshots(db_session, [second_id, third_id])

    _change(event, changed_id, db_session, purpose="Breakout session", expected_occupancy=20)

    assert _snapshots(db_session, [second_id, third_id]) == others_before
    changed_entries = _changed_entries(db_session)
    assert len(changed_entries) == 1
    assert changed_entries[0].details["venue_booking_request_id"] == changed_id


def test_changing_writes_the_previous_and_new_value_to_history(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)

    _change(event, arrangement.id, db_session, purpose="Breakout session")

    entries = _changed_entries(db_session)
    assert len(entries) == 1
    assert entries[0].actor_id == COORDINATOR_ID
    assert entries[0].details == {
        "venue_booking_request_id": arrangement.id,
        "venue_id": venue.id,
        "changes": {"purpose": {"previous": "Main hall", "new": "Breakout session"}},
    }


def test_a_change_that_alters_nothing_writes_no_history(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)

    _change(event, arrangement.id, db_session, purpose=arrangement.purpose)

    assert _changed_entries(db_session) == []


def test_an_empty_payload_is_accepted_and_changes_nothing(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)

    shown = _change(event, arrangement.id, db_session)

    assert shown.request.purpose == arrangement.purpose
    assert _changed_entries(db_session) == []


def test_sending_the_layout_as_null_clears_it_without_needing_a_justification(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session, required_layout="theatre")

    shown = _change(event, arrangement.id, db_session, required_layout=None)

    assert shown.request.required_layout is None
    entries = _changed_entries(db_session)
    assert len(entries) == 1
    assert entries[0].details["changes"] == {
        "required_layout": {"previous": "theatre", "new": None}
    }


def test_sending_a_null_layout_when_there_is_none_changes_nothing(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)

    shown = _change(event, arrangement.id, db_session, required_layout=None)

    assert shown.request.required_layout is None
    assert _changed_entries(db_session) == []


def test_raising_the_occupancy_past_the_venues_capacity_needs_a_justification(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """A refused change leaves the row untouched, even a field that was valid."""
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session, expected_occupancy=50)

    with pytest.raises(ValidationError) as caught:
        _change(
            event,
            arrangement.id,
            db_session,
            purpose="Plenary",
            expected_occupancy=venue.capacity + 1,
        )

    assert caught.value.details == {"justification": [UNSUITABLE_MESSAGE]}
    assert arrangement.expected_occupancy == 50
    assert arrangement.purpose == "Main hall"
    assert _changed_entries(db_session) == []


def test_an_unsuitable_occupancy_is_allowed_with_a_justification(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session, expected_occupancy=50)

    shown = _change(
        event,
        arrangement.id,
        db_session,
        expected_occupancy=venue.capacity + 1,
        justification="Only hall free",
    )

    assert shown.request.expected_occupancy == venue.capacity + 1


def test_a_justification_already_on_the_arrangement_still_counts(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The stored justification is merged in, so it need not be sent again."""
    event = saved_event()
    arrangement = raise_booking(
        venue,
        event,
        db_session,
        expected_occupancy=venue.capacity + 5,
        justification="Only hall free",
    )

    shown = _change(event, arrangement.id, db_session, expected_occupancy=venue.capacity + 6)

    assert shown.request.expected_occupancy == venue.capacity + 6


def test_a_withdrawn_arrangement_cannot_be_changed(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)
    services.withdraw_arrangement(
        event.reference, arrangement.id, coordinator_id=COORDINATOR_ID, session=db_session
    )

    with pytest.raises(ConflictError) as caught:
        _change(event, arrangement.id, db_session, purpose="Breakout session")

    assert caught.value.message == (
        "Only a pending arrangement can be changed; this one is withdrawn."
    )


def test_a_blank_purpose_is_a_validation_error(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)

    with pytest.raises(ValidationError) as caught:
        _change(event, arrangement.id, db_session, purpose="   ")

    assert "purpose" in caught.value.details


def test_another_events_arrangement_cannot_be_changed(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    mine = saved_event()
    theirs = saved_event()
    theirs_arrangement = raise_booking(venue, theirs, db_session)

    with pytest.raises(NotFoundError):
        _change(mine, theirs_arrangement.id, db_session, purpose="Breakout session")
