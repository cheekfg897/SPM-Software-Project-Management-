"""Unit tests for SCRUM-92 — what a flag does to the event, and who is told.

AC3: a Confirmed event goes back to Approved, the planning stage, and its organiser is
told, naming the event and the venue (Product Owner, 25 Oct); an event at any other
status keeps it, and its organiser hears nothing. AC4: the event and its original
booking stay on the record. AC5: the event's assigned coordinator is notified with the
venue, the reason and the period; a notice that can't be saved loses only itself
(ADR-0015). SCRUM-49 AC6: an event with a flagged booking can't be confirmed, and the
flagged booking is named (ADR-0053).

The services run against ``db_session``; the event is the ``saved_event`` fixture's,
assigned to coordinator 3, with an arrangement from 09:00 to 12:00 on 1 November 2026.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import services as event_services
from app.modules.events.models import (
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from tests.venue.conftest import (
    COORDINATOR_ID,
    DEACTIVATED_AT,
    DEACTIVATION,
    SavedEvent,
    approve_safety,
    at,
    block,
    decide,
    history_entries,
    hours_from_now,
    place_hold,
    raise_booking,
    reload_event,
    reload_request,
)

pytestmark = pytest.mark.scrum_92

#: A coordinator who did not raise the request; the event is reassigned to them.
REASSIGNED_COORDINATOR_ID = 9
ORGANISER_ID = 7
BLOCK_DETAIL = (
    "Main Hall is unavailable from 2026-11-01 10:00 to 2026-11-01 11:00"
    " (equipment failure): Lift broken."
)
DEACTIVATION_DETAIL = (
    "Main Hall is unavailable from 2026-10-20 12:00 until it is reactivated"
    " (renovation): Closed for a refit."
)
#: What the organiser is told when the venue sends their Confirmed event back (AC3).
ORGANISER_DETAIL = (
    "Main Hall became unavailable for Partner Summit, so the event has gone back from"
    " Confirmed to Approved for its venue to be reviewed. It has not been cancelled."
)
NOT_CONFIRMED = [
    status for status in EventRequestStatus if status is not EventRequestStatus.CONFIRMED
]
LOST_CONNECTION = OperationalError("INSERT INTO notifications", {}, Exception("lost"))


def _block_with_lift_broken(venue: Venue, session: Session) -> None:
    block(venue, at(10), at(11), session, category="equipment_failure", reason="Lift broken.")


def _deactivate(venue: Venue, session: Session) -> None:
    services.deactivate_venue(venue.id, DEACTIVATION, session=session, now=DEACTIVATED_AT)


def _lose_connection(*_: Any, **__: Any) -> None:
    raise LOST_CONNECTION


def _notices(user_id: int) -> list[tuple[int, NotificationKind, str | None]]:
    """The user's notifications as (event id, kind, detail), newest first.

    Only this story's kind: the decisions the tests set up notify the coordinator too.
    """
    rows = []
    for notification in list_notifications_for_recipient(user_id):
        if notification.kind is NotificationKind.ALTERNATIVE_VENUE_NEEDED:
            rows.append((notification.event_request_id, notification.kind, notification.detail))
    return rows


def _history(session: Session, event_id: int) -> list[tuple[EventHistoryKind, Any, Any]]:
    """The event's history entries as (kind, actor id, details), oldest first."""
    rows = []
    for entry in history_entries(session, event_id):
        rows.append((entry.kind, entry.actor_id, entry.details))
    return rows


def _arranged(
    venue: Venue, saved_event: SavedEvent, session: Session, status: EventRequestStatus
) -> tuple[EventRequest, VenueBookingRequest]:
    """An event at ``status`` with one Approved arrangement at ``venue``."""
    event = saved_event()
    approved = decide(raise_booking(venue, event, session).id, "approved", session)
    event.status = status
    session.commit()
    return event, approved


# --------------------------------------------------------------------------
# AC3 — a Confirmed event goes back to Approved; any other keeps its status
# --------------------------------------------------------------------------


def test_a_confirmed_event_goes_back_to_approved_and_the_history_says_why(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, approved = _arranged(venue, saved_event, db_session, EventRequestStatus.CONFIRMED)

    _block_with_lift_broken(venue, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    assert _history(db_session, event.id)[-1] == (
        EventHistoryKind.ALTERNATIVE_VENUE_NEEDED,
        None,
        {
            "venue_booking_request_id": approved.id,
            "venue_id": venue.id,
            "category": "equipment_failure",
            "reason": "Lift broken.",
            "starts_at": "2026-11-01T02:00:00+00:00",
            "ends_at": "2026-11-01T03:00:00+00:00",
            "returned_to_planning": True,
        },
    )


@pytest.mark.parametrize("status", NOT_CONFIRMED)
def test_an_event_that_is_not_confirmed_keeps_its_status(
    db_session: Session, venue: Venue, saved_event: SavedEvent, status: EventRequestStatus
) -> None:
    event, _ = _arranged(venue, saved_event, db_session, status)

    _block_with_lift_broken(venue, db_session)

    assert reload_event(db_session, event.id).status is status
    kind, _, details = _history(db_session, event.id)[-1]
    assert kind is EventHistoryKind.ALTERNATIVE_VENUE_NEEDED
    assert details["returned_to_planning"] is False


@pytest.mark.parametrize(
    "make_unavailable",
    [
        pytest.param(_block_with_lift_broken, id="a block"),
        pytest.param(_deactivate, id="a deactivation"),
    ],
)
def test_the_organiser_is_told_their_confirmed_event_went_back_to_approved(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    make_unavailable: Callable[[Venue, Session], None],
) -> None:
    """The Product Owner, 25 Oct: the notice names the event and the venue (AC3).

    Venue Staff's note stays out of it, as it does of the organiser's history.
    """
    event, _ = _arranged(venue, saved_event, db_session, EventRequestStatus.CONFIRMED)

    make_unavailable(venue, db_session)

    assert _notices(ORGANISER_ID) == [
        (event.id, NotificationKind.ALTERNATIVE_VENUE_NEEDED, ORGANISER_DETAIL)
    ]


def test_the_coordinator_is_told_the_reason_and_not_the_organisers_notice(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, _ = _arranged(venue, saved_event, db_session, EventRequestStatus.CONFIRMED)

    _block_with_lift_broken(venue, db_session)

    assert _notices(COORDINATOR_ID) == [
        (event.id, NotificationKind.ALTERNATIVE_VENUE_NEEDED, BLOCK_DETAIL)
    ]


@pytest.mark.parametrize("status", NOT_CONFIRMED)
def test_the_organiser_of_an_event_that_is_not_confirmed_is_not_told(
    db_session: Session, venue: Venue, saved_event: SavedEvent, status: EventRequestStatus
) -> None:
    """Its status doesn't change, so there is nothing to tell them (AC3)."""
    _arranged(venue, saved_event, db_session, status)

    _block_with_lift_broken(venue, db_session)

    assert _notices(ORGANISER_ID) == []


def test_the_organiser_is_told_once_when_one_block_flags_two_of_its_arrangements(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The first flag sends the event back; the second finds it Approved already."""
    event = saved_event()
    raise_booking(venue, event, db_session)
    raise_booking(
        venue, event, db_session, starts_at=at(13).isoformat(), ends_at=at(15).isoformat()
    )
    event.status = EventRequestStatus.CONFIRMED
    db_session.commit()

    block(venue, at(8), at(16), db_session)

    assert _notices(ORGANISER_ID) == [
        (event.id, NotificationKind.ALTERNATIVE_VENUE_NEEDED, ORGANISER_DETAIL)
    ]


def test_a_deactivation_is_written_to_the_history_with_no_end(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, approved = _arranged(venue, saved_event, db_session, EventRequestStatus.CONFIRMED)

    _deactivate(venue, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    assert _history(db_session, event.id)[-1][2] == {
        "venue_booking_request_id": approved.id,
        "venue_id": venue.id,
        "category": "renovation",
        "reason": "Closed for a refit.",
        "starts_at": "2026-10-20T04:00:00+00:00",
        "ends_at": None,
        "returned_to_planning": True,
    }


def test_the_history_entry_is_for_internal_eyes_only(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    saved_users: list[User],
) -> None:
    """The note is Venue Staff's; the calendar hides it from others too (ADR-0053)."""
    event, _ = _arranged(venue, saved_event, db_session, EventRequestStatus.CONFIRMED)
    event.organisation_id = 3
    db_session.commit()

    _block_with_lift_broken(venue, db_session)

    organiser_sees = event_services.list_event_history(
        ORGANISER_ID, event.reference, viewer_role=Role.EVENT_ORGANISER, session=db_session
    )
    coordinator_sees = event_services.list_event_history(
        COORDINATOR_ID, event.reference, viewer_role=Role.EVENT_COORDINATOR, session=db_session
    )
    alternative = EventHistoryKind.ALTERNATIVE_VENUE_NEEDED
    assert alternative not in [entry.kind for entry in organiser_sees]
    assert alternative in [entry.kind for entry in coordinator_sees]


def test_a_block_that_flags_nothing_leaves_the_event_alone(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, _ = _arranged(venue, saved_event, db_session, EventRequestStatus.CONFIRMED)

    block(venue, at(13), at(14), db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.CONFIRMED
    assert _notices(COORDINATOR_ID) == []


# --------------------------------------------------------------------------
# AC4 — the event and its original booking stay on the record
# --------------------------------------------------------------------------


def test_the_event_keeps_its_details_and_its_flagged_booking(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, approved = _arranged(venue, saved_event, db_session, EventRequestStatus.CONFIRMED)

    _block_with_lift_broken(venue, db_session)

    kept = reload_event(db_session, event.id)
    assert (kept.name, kept.expected_attendance) == ("Partner Summit", 80)
    listed = services.list_booking_requests_for_event(
        event.reference, coordinator_id=COORDINATOR_ID, session=db_session
    )
    assert [(shown.request.id, shown.request.status) for shown in listed] == [
        (approved.id, BookingRequestStatus.APPROVED)
    ]
    assert listed[0].request.needs_alternative_venue is True


# --------------------------------------------------------------------------
# AC5 — the assigned coordinator is told the venue, the reason and the period
# --------------------------------------------------------------------------


def test_the_assigned_coordinator_is_told_the_venue_the_reason_and_the_period(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The event was reassigned after the request: its coordinator now is told."""
    event, _ = _arranged(venue, saved_event, db_session, EventRequestStatus.APPROVED)
    event.coordinator_id = REASSIGNED_COORDINATOR_ID
    db_session.commit()

    _block_with_lift_broken(venue, db_session)

    assert _notices(REASSIGNED_COORDINATOR_ID) == [
        (event.id, NotificationKind.ALTERNATIVE_VENUE_NEEDED, BLOCK_DETAIL)
    ]
    assert _notices(COORDINATOR_ID) == []


def test_a_deactivation_tells_the_coordinator_it_lasts_until_reactivated(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, _ = _arranged(venue, saved_event, db_session, EventRequestStatus.APPROVED)

    _deactivate(venue, db_session)

    assert _notices(COORDINATOR_ID) == [
        (event.id, NotificationKind.ALTERNATIVE_VENUE_NEEDED, DEACTIVATION_DETAIL)
    ]


def test_each_flagged_arrangement_is_its_own_notice(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    first_event, _ = _arranged(venue, saved_event, db_session, EventRequestStatus.APPROVED)
    second_event = saved_event()
    raise_booking(
        venue, second_event, db_session, starts_at=at(13).isoformat(), ends_at=at(15).isoformat()
    )

    block(venue, at(8), at(16), db_session)

    assert sorted(event_id for event_id, _, _ in _notices(COORDINATOR_ID)) == [
        first_event.id,
        second_event.id,
    ]


def test_an_event_with_no_coordinator_is_flagged_and_nobody_is_told(
    db_session: Session, venue: Venue, saved_event: SavedEvent, caplog: pytest.LogCaptureFixture
) -> None:
    event, approved = _arranged(venue, saved_event, db_session, EventRequestStatus.APPROVED)
    event.coordinator_id = None
    db_session.commit()

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _block_with_lift_broken(venue, db_session)

    assert reload_request(db_session, approved.id).needs_alternative_venue is True
    assert _notices(COORDINATOR_ID) == []
    assert f"event_request_unassigned reference={event.reference}" in caplog.text


@pytest.mark.parametrize(
    "make_unavailable",
    [
        pytest.param(_block_with_lift_broken, id="a block"),
        pytest.param(_deactivate, id="a deactivation"),
    ],
)
def test_a_notice_that_cannot_be_saved_leaves_the_flag_and_the_status_change(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    make_unavailable: Callable[[Venue, Session], None],
) -> None:
    """The flag and the status are committed before the notice (ADR-0015)."""
    event, approved = _arranged(venue, saved_event, db_session, EventRequestStatus.CONFIRMED)
    monkeypatch.setattr(event_services, "notify_users", _lose_connection)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        make_unavailable(venue, db_session)

    db_session.rollback()
    assert reload_request(db_session, approved.id).needs_alternative_venue is True
    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    assert "kind=alternative_venue_needed" in caplog.text


# --------------------------------------------------------------------------
# SCRUM-49 AC6 — a flagged booking keeps the event from being confirmed
# --------------------------------------------------------------------------


def test_confirmation_is_refused_while_a_booking_needs_an_alternative_venue(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, approved = _arranged(venue, saved_event, db_session, EventRequestStatus.SAFETY_REVIEW)
    approve_safety(event, db_session)
    blocked = block(venue, at(10), at(11), db_session)

    with pytest.raises(event_services.EventConfirmationNotAllowedError) as refusal:
        event_services.confirm_event_request(COORDINATOR_ID, event.reference, session=db_session)

    assert refusal.value.details == {
        "venue_arrangements": [f"Venue arrangement {approved.id} needs an alternative venue."]
    }

    services.remove_venue_block(venue.id, blocked.id, session=db_session)
    confirmed = event_services.confirm_event_request(
        COORDINATOR_ID, event.reference, session=db_session
    )
    assert confirmed.status is EventRequestStatus.CONFIRMED


def test_the_safety_review_gate_names_the_flagged_booking_too(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """SCRUM-97 shares the venue check with confirmation (ADR-0053)."""
    event, approved = _arranged(venue, saved_event, db_session, EventRequestStatus.APPROVED)
    block(venue, at(10), at(11), db_session)

    with pytest.raises(event_services.SafetyReviewNotAllowedError) as refusal:
        event_services.submit_for_safety_review(COORDINATOR_ID, event.reference, session=db_session)

    assert refusal.value.details == {
        "venue_arrangements": [f"Venue arrangement {approved.id} needs an alternative venue."]
    }


def test_the_safety_review_gate_names_a_flagged_hold_as_needing_an_alternative_venue(
    db_session: Session, multi_venue_event: EventRequest, multi_venue_request: VenueBookingRequest
) -> None:
    """A request On Hold is flagged too (ADR-0100), so the gate names both its gaps."""
    held = place_hold(multi_venue_request.id, hours_from_now(24), db_session)
    held_venue = db_session.get(Venue, held.venue_id)
    assert held_venue is not None
    block(held_venue, at(10), at(11), db_session)
    [_, breakout] = services.list_active_arrangements(multi_venue_event.id, session=db_session)

    with pytest.raises(event_services.SafetyReviewNotAllowedError) as refusal:
        event_services.submit_for_safety_review(
            COORDINATOR_ID, multi_venue_event.reference, session=db_session
        )

    assert refusal.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {held.id} is on_hold.",
            f"Venue arrangement {breakout.id} is pending.",
            f"Venue arrangement {held.id} needs an alternative venue.",
        ]
    }


def test_a_released_flagged_arrangement_does_not_hold_the_event_back(
    db_session: Session, venue: Venue, saved_event: SavedEvent, make_venue: Callable[..., Venue]
) -> None:
    """Once released it is retired, like a withdrawn one (SCRUM-93, AC7)."""
    event, approved = _arranged(venue, saved_event, db_session, EventRequestStatus.SAFETY_REVIEW)
    approve_safety(event, db_session)
    block(venue, at(10), at(11), db_session)
    approved.status = BookingRequestStatus.RELEASED
    db_session.commit()
    other = make_venue(name="Annex")
    db_session.add(other)
    db_session.commit()
    replacement = VenueBookingRequest(
        event_id=event.id,
        venue_id=other.id,
        starts_at=approved.starts_at,
        ends_at=approved.ends_at,
        purpose="Main hall",
        expected_occupancy=80,
        status=BookingRequestStatus.APPROVED,
        requested_by=COORDINATOR_ID,
    )
    db_session.add(replacement)
    db_session.commit()

    confirmed = event_services.confirm_event_request(
        COORDINATOR_ID, event.reference, session=db_session
    )

    assert confirmed.status is EventRequestStatus.CONFIRMED
