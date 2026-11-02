"""Unit tests for every one of an event's venue arrangements, as its record shows them.

SCRUM-24 AC10 (Product Owner, 25 Oct): the Event Organiser sees every venue
arrangement with its status at every stage, including holds with their expiry and
flags with their reason, and nothing on the record is hidden from them (ADR-0104).
SCRUM-93 AC5: every arrangement and its status is listed on the event record, and an On
Hold one shows its hold expiry, or that it has expired. The events module reads them
through ``list_every_arrangement_for_record``, never the venue models.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest
from app.modules.venue import services
from app.modules.venue.models import (
    AlternativeVenueFlag,
    BookingRequestStatus,
    PreparationStatus,
    ReassessmentFlag,
    ReassessmentFlagKind,
    UnavailabilityCategory,
    Venue,
    VenueBookingRequest,
)
from app.modules.venue.services import (
    ArrangementForRecord,
    ReassessmentForRecord,
    UnavailabilityForRecord,
)
from tests.conftest import HOLD_STATUSES, place_hold_on
from tests.venue.conftest import COORDINATOR_ID

pytestmark = pytest.mark.scrum_24

SaveArrangement = Callable[..., VenueBookingRequest]
#: When the hold in these tests runs out: 25 October 2026, 17:00 in Singapore.
HOLD_EXPIRY = datetime(2026, 10, 25, 9, tzinfo=UTC)


def _hours(hour: int) -> tuple[datetime, datetime]:
    """An hour-long period on 1 November 2026 from ``hour`` UTC."""
    return datetime(2026, 11, 1, hour, tzinfo=UTC), datetime(2026, 11, 1, hour + 1, tzinfo=UTC)


@pytest.fixture()
def save_arrangement(save: Callable[..., None]) -> SaveArrangement:
    """Save an arrangement of ``event`` at ``venue`` from ``hour`` UTC for an hour."""

    def _save(
        event: EventRequest,
        venue: Venue,
        *,
        hour: int,
        status: BookingRequestStatus = BookingRequestStatus.PENDING,
    ) -> VenueBookingRequest:
        starts_at, ends_at = _hours(hour)
        arrangement = VenueBookingRequest(
            event_id=event.id,
            venue_id=venue.id,
            starts_at=starts_at,
            ends_at=ends_at,
            purpose="Main session",
            expected_occupancy=80,
            status=status,
            requested_by=COORDINATOR_ID,
        )
        save(arrangement)
        return arrangement

    return _save


def test_every_arrangement_is_listed_with_its_status_earliest_first(
    db_session: Session,
    venue: Venue,
    saved_event: Callable[..., EventRequest],
    save_arrangement: SaveArrangement,
    save: Callable[..., None],
) -> None:
    """Withdrawn, released, rejected and expired ones too, saved latest period first."""
    event = saved_event()
    every_status = list(BookingRequestStatus)
    for hour, status in reversed(list(enumerate(every_status))):
        arrangement = save_arrangement(event, venue, hour=hour, status=status)
        if status in HOLD_STATUSES:
            place_hold_on(arrangement, HOLD_EXPIRY, save)

    shown = services.list_every_arrangement_for_record(event.id, session=db_session)

    assert [arrangement.status for arrangement in shown] == every_status


def test_an_arrangement_shows_everything_on_it(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: Callable[..., EventRequest],
    save_arrangement: SaveArrangement,
) -> None:
    event = saved_event()
    hall = make_venue(
        name="Main Hall",
        location="Building A",
        capacity=250,
        facilities="stage,pa system",
        accessibility_features="hearing loop",
    )
    save(hall)
    arrangement = save_arrangement(event, hall, hour=1, status=BookingRequestStatus.REJECTED)
    arrangement.required_layout = "theatre"
    arrangement.justification = "Only hall free that week."
    arrangement.decision_reason = "The hall is being repainted."
    arrangement.preparation_status = PreparationStatus.IN_PROGRESS
    arrangement.preparation_notes = "Chairs set out."
    save(arrangement)

    shown = services.list_every_arrangement_for_record(event.id, session=db_session)

    assert shown == [
        ArrangementForRecord(
            venue_name="Main Hall",
            venue_location="Building A",
            venue_capacity=250,
            venue_facilities=["stage", "pa system"],
            venue_accessibility_features=["hearing loop"],
            starts_at=datetime(2026, 11, 1, 1, tzinfo=UTC),
            ends_at=datetime(2026, 11, 1, 2, tzinfo=UTC),
            purpose="Main session",
            expected_occupancy=80,
            required_layout="theatre",
            justification="Only hall free that week.",
            status=BookingRequestStatus.REJECTED,
            decision_reason="The hall is being repainted.",
            suggested_venue_name=None,
            suggested_starts_at=None,
            suggested_ends_at=None,
            hold_expires_at=None,
            needs_alternative_venue=False,
            unavailability=[],
            flagged_after_change=False,
            reassessment_flags=[],
            preparation_status=PreparationStatus.IN_PROGRESS,
            preparation_notes="Chairs set out.",
        )
    ]


@pytest.mark.parametrize("status", HOLD_STATUSES, ids=lambda status: status.value)
def test_a_hold_shows_when_it_expires_or_expired(
    db_session: Session,
    venue: Venue,
    saved_event: Callable[..., EventRequest],
    save_arrangement: SaveArrangement,
    save: Callable[..., None],
    status: BookingRequestStatus,
) -> None:
    event = saved_event()
    place_hold_on(save_arrangement(event, venue, hour=1, status=status), HOLD_EXPIRY, save)

    shown = services.list_every_arrangement_for_record(event.id, session=db_session)

    assert [arrangement.hold_expires_at for arrangement in shown] == [HOLD_EXPIRY]


def test_an_arrangement_with_no_hold_shows_no_expiry(
    db_session: Session,
    venue: Venue,
    saved_event: Callable[..., EventRequest],
    save_arrangement: SaveArrangement,
    save: Callable[..., None],
) -> None:
    """Once a hold is approved it is a booking: its old expiry no longer applies."""
    event = saved_event()
    approved = save_arrangement(event, venue, hour=1, status=BookingRequestStatus.APPROVED)
    place_hold_on(approved, HOLD_EXPIRY, save)

    shown = services.list_every_arrangement_for_record(event.id, session=db_session)

    assert [arrangement.hold_expires_at for arrangement in shown] == [None]


def test_a_flagged_arrangement_shows_each_flag_with_its_reason(
    db_session: Session,
    venue: Venue,
    save: Callable[..., None],
    saved_event: Callable[..., EventRequest],
    save_arrangement: SaveArrangement,
) -> None:
    event = saved_event()
    arrangement = save_arrangement(event, venue, hour=1, status=BookingRequestStatus.APPROVED)
    arrangement.flags.append(
        AlternativeVenueFlag(
            category=UnavailabilityCategory.MAINTENANCE,
            reason="Aircon repair.",
            starts_at=datetime(2026, 11, 1, 0, tzinfo=UTC),
            ends_at=None,
        )
    )
    arrangement.reassessment_flags.append(
        ReassessmentFlag(
            kind=ReassessmentFlagKind.NO_LONGER_SUITABLE,
            reason="Expected attendance rose to 120; the venue holds 100.",
        )
    )
    save(arrangement)

    [shown] = services.list_every_arrangement_for_record(event.id, session=db_session)

    assert (shown.needs_alternative_venue, shown.flagged_after_change) == (True, True)
    assert shown.unavailability == [
        UnavailabilityForRecord(
            category=UnavailabilityCategory.MAINTENANCE,
            reason="Aircon repair.",
            starts_at=datetime(2026, 11, 1, 0, tzinfo=UTC),
            ends_at=None,
        )
    ]
    assert shown.reassessment_flags == [
        ReassessmentForRecord(
            kind=ReassessmentFlagKind.NO_LONGER_SUITABLE,
            reason="Expected attendance rose to 120; the venue holds 100.",
        )
    ]


def test_another_events_arrangements_are_left_out(
    db_session: Session,
    venue: Venue,
    saved_event: Callable[..., EventRequest],
    save_arrangement: SaveArrangement,
) -> None:
    event = saved_event()
    other_event = saved_event()
    save_arrangement(other_event, venue, hour=1)

    assert services.list_every_arrangement_for_record(event.id, session=db_session) == []
