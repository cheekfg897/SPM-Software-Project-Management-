"""Unit tests for SCRUM-70 — Venue Staff suggest an alternative when they reject.

AC1: rejecting may suggest one alternative venue, one alternative period, or both, and
only rejecting may; a replacement for a booking whose venue became unavailable keeps
that booking's period (SCRUM-92), so only a venue may be suggested for it. AC2: the
suggested venue must be active, and the suggested period is not checked until the
coordinator raises a request for it. AC3: the suggestion is on the request, in the
decision's history entry and on the event's record, the venue by name. AC4: the
coordinator raises an ordinary new request from it, and the rejected one stays as it
is. AC5: a suggestion books and holds nothing. AC6: the event's current coordinator is
told once, by the rejection notice, which names the suggestion before the reason
(SCRUM-115, ADR-0123).

The services run against ``db_session``. The request to reject is at the Auditorium,
09:00 to 12:00 on 1 November 2026; the Breakout room is suggested instead.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.events.models import EventHistoryKind, EventRequest
from app.modules.events.schemas import RecordVenueArrangementSchema
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.venue import services
from app.modules.venue.models import (
    BookingRequestStatus,
    BookingStatus,
    ReassessmentFlag,
    ReassessmentFlagKind,
    Venue,
    VenueBookingRequest,
)
from app.modules.venue.schemas import BookingRequestAsShown, VenueBookingRequestSchema
from tests.venue.conftest import (
    COORDINATOR_ID,
    VENUE_STAFF_ID,
    SavedEvent,
    at,
    block,
    bookings,
    decide,
    history_entries,
    hours_from_now,
    period,
    place_hold,
    raise_booking,
    reload_request,
    two_venues,
)

pytestmark = pytest.mark.scrum_70

REASON = "The Auditorium is being repainted."
#: 3 November 2026, 14:00 to 17:00 in Singapore, as the client sends it.
SUGGESTED_PERIOD = period(at(14, day=3), at(17, day=3))
SUGGESTED_TIMES = {
    "suggested_starts_at": SUGGESTED_PERIOD["starts_at"],
    "suggested_ends_at": SUGGESTED_PERIOD["ends_at"],
}
SUGGESTED_STARTS_UTC = datetime(2026, 11, 3, 6, 0, tzinfo=UTC)
SUGGESTED_ENDS_UTC = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
ONLY_WHEN_REJECTING = "An alternative can only be suggested when rejecting a request."
NOT_ACTIVE = "The suggested venue must be an active venue."
PERIOD_LOCKED = (
    "A replacement keeps the period of the booking it replaces, so only another venue can"
    " be suggested."
)
NOT_WHOLE = "A suggested period needs both a start and an end."
ENDS_BEFORE_START = "suggested_ends_at must be after suggested_starts_at."


class Rejectable:
    """A Pending request at the Auditorium, its event, and the Breakout room."""

    def __init__(self, event: EventRequest, request: VenueBookingRequest, other: Venue) -> None:
        self.event = event
        self.request = request
        self.other = other


@pytest.fixture()
def rejectable(
    db_session: Session,
    saved_users: list[User],
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> Rejectable:
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    return Rejectable(event, raise_booking(auditorium, event, db_session), breakout)


def _decide(
    request_id: int, session: Session, outcome: str = "rejected", **suggestion: Any
) -> VenueBookingRequest:
    """Decide the request as Venue Staff, with a reason and ``suggestion``."""
    payload = {"outcome": outcome, "reason": REASON, **suggestion}
    shown = services.decide_booking_request(
        request_id, payload, decided_by=VENUE_STAFF_ID, session=session
    )
    return shown.request


def _refusal(request_id: int, session: Session, **payload: Any) -> dict[str, list[str]]:
    """The per-field messages of a decision refused with a 400."""
    with pytest.raises(ValidationError) as refusal:
        _decide(request_id, session, **payload)
    assert refusal.value.status_code == 400
    return refusal.value.details


def _suggestion(session: Session, request_id: int) -> tuple[Any, ...]:
    """The suggestion stored on the request, read back from the database."""
    stored = reload_request(session, request_id)
    return (stored.suggested_venue_id, stored.suggested_starts_at, stored.suggested_ends_at)


def _assert_still_pending(session: Session, request_id: int) -> None:
    """A refused decision leaves the request waiting, suggesting and booking nothing."""
    assert reload_request(session, request_id).status is BookingRequestStatus.PENDING
    assert _suggestion(session, request_id) == (None, None, None)
    assert bookings(session) == []


# --------------------------------------------------------------------------
# AC1 — one venue, one period, or both, only while rejecting
# --------------------------------------------------------------------------


def test_rejecting_may_suggest_another_venue(db_session: Session, rejectable: Rejectable) -> None:
    rejected = _decide(rejectable.request.id, db_session, suggested_venue_id=rejectable.other.id)

    assert rejected.status is BookingRequestStatus.REJECTED
    assert _suggestion(db_session, rejected.id) == (rejectable.other.id, None, None)


def test_a_conflicting_request_may_be_rejected_with_a_suggestion(
    db_session: Session, rejectable: Rejectable, saved_event: SavedEvent
) -> None:
    """Venue Staff decide a Conflicting request too (ADR-0045).

    Another event's request for the same period was approved first.
    """
    auditorium = db_session.get(Venue, rejectable.request.venue_id)
    clashing = raise_booking(auditorium, saved_event(), db_session)
    decide(clashing.id, "approved", db_session)
    assert reload_request(db_session, rejectable.request.id).status is (
        BookingRequestStatus.CONFLICTING
    )

    rejected = _decide(rejectable.request.id, db_session, suggested_venue_id=rejectable.other.id)

    assert rejected.status is BookingRequestStatus.REJECTED
    assert _suggestion(db_session, rejected.id) == (rejectable.other.id, None, None)


def test_a_held_request_may_be_rejected_with_a_suggestion_and_its_hold_is_let_go(
    db_session: Session, multi_venue_event: EventRequest
) -> None:
    """Venue Staff decide an On Hold request too (SCRUM-75), on a multi-venue event.

    The suggestion holds nothing (AC5), and the rejection still cancels the hold. The
    suggested venue is the event's other one.
    """
    [held, other] = services.list_active_arrangements(multi_venue_event.id, session=db_session)
    place_hold(held.id, hours_from_now(48), db_session)

    rejected = _decide(held.id, db_session, suggested_venue_id=other.venue_id)

    assert rejected.status is BookingRequestStatus.REJECTED
    assert _suggestion(db_session, rejected.id) == (other.venue_id, None, None)
    assert bookings(db_session) == [(held.venue_id, BookingStatus.CANCELLED)]


def test_rejecting_may_suggest_another_period_stored_in_utc(
    db_session: Session, rejectable: Rejectable
) -> None:
    rejected = _decide(rejectable.request.id, db_session, **SUGGESTED_TIMES)

    assert _suggestion(db_session, rejected.id) == (
        None,
        SUGGESTED_STARTS_UTC,
        SUGGESTED_ENDS_UTC,
    )


def test_rejecting_may_suggest_another_venue_and_another_period(
    db_session: Session, rejectable: Rejectable
) -> None:
    rejected = _decide(
        rejectable.request.id,
        db_session,
        suggested_venue_id=rejectable.other.id,
        **SUGGESTED_TIMES,
    )

    assert _suggestion(db_session, rejected.id) == (
        rejectable.other.id,
        SUGGESTED_STARTS_UTC,
        SUGGESTED_ENDS_UTC,
    )


def test_a_suggested_period_with_no_offset_is_read_as_business_time(
    db_session: Session, rejectable: Rejectable
) -> None:
    """As every other time sent to the backend is (ADR-0009)."""
    rejected = _decide(
        rejectable.request.id,
        db_session,
        suggested_starts_at="2026-11-03T14:00:00",
        suggested_ends_at="2026-11-03T17:00:00",
    )

    assert _suggestion(db_session, rejected.id) == (
        None,
        SUGGESTED_STARTS_UTC,
        SUGGESTED_ENDS_UTC,
    )


def test_rejecting_without_a_suggestion_stores_none(
    db_session: Session, rejectable: Rejectable
) -> None:
    """A suggestion is optional (customer, Week 4 A44)."""
    rejected = _decide(rejectable.request.id, db_session)

    assert _suggestion(db_session, rejected.id) == (None, None, None)


def test_a_suggestion_sent_as_nulls_is_no_suggestion(
    db_session: Session, rejectable: Rejectable
) -> None:
    """What a client sending all three fields every time sends to suggest nothing."""
    rejected = _decide(
        rejectable.request.id,
        db_session,
        suggested_venue_id=None,
        suggested_starts_at=None,
        suggested_ends_at=None,
    )

    assert _suggestion(db_session, rejected.id) == (None, None, None)


def test_approving_with_a_suggested_venue_is_refused(
    db_session: Session, rejectable: Rejectable
) -> None:
    details = _refusal(
        rejectable.request.id,
        db_session,
        outcome="approved",
        suggested_venue_id=rejectable.other.id,
    )

    assert details == {"suggested_venue_id": [ONLY_WHEN_REJECTING]}
    _assert_still_pending(db_session, rejectable.request.id)


def test_approving_with_a_suggested_period_is_refused_on_both_its_fields(
    db_session: Session, rejectable: Rejectable
) -> None:
    details = _refusal(rejectable.request.id, db_session, outcome="approved", **SUGGESTED_TIMES)

    assert details == {
        "suggested_starts_at": [ONLY_WHEN_REJECTING],
        "suggested_ends_at": [ONLY_WHEN_REJECTING],
    }
    _assert_still_pending(db_session, rejectable.request.id)


# --------------------------------------------------------------------------
# AC1 — the suggested period is a whole period, and the venue id a whole number
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        pytest.param(
            {"suggested_starts_at": SUGGESTED_PERIOD["starts_at"]},
            {"suggested_ends_at": [NOT_WHOLE]},
            id="a start with no end",
        ),
        pytest.param(
            {"suggested_ends_at": SUGGESTED_PERIOD["ends_at"]},
            {"suggested_starts_at": [NOT_WHOLE]},
            id="an end with no start",
        ),
        pytest.param(
            {
                "suggested_starts_at": SUGGESTED_PERIOD["ends_at"],
                "suggested_ends_at": SUGGESTED_PERIOD["starts_at"],
            },
            {"suggested_ends_at": [ENDS_BEFORE_START]},
            id="an end before the start",
        ),
        pytest.param(
            {
                "suggested_starts_at": SUGGESTED_PERIOD["starts_at"],
                "suggested_ends_at": SUGGESTED_PERIOD["starts_at"],
            },
            {"suggested_ends_at": [ENDS_BEFORE_START]},
            id="an end at the start",
        ),
        pytest.param(
            {"suggested_starts_at": "tomorrow", "suggested_ends_at": "later"},
            {
                "suggested_starts_at": ["Not a valid datetime."],
                "suggested_ends_at": ["Not a valid datetime."],
            },
            id="times that are not times",
        ),
    ],
)
def test_a_suggested_period_that_is_not_a_whole_period_is_refused(
    db_session: Session,
    rejectable: Rejectable,
    sent: dict[str, str],
    expected: dict[str, list[str]],
) -> None:
    assert _refusal(rejectable.request.id, db_session, **sent) == expected
    _assert_still_pending(db_session, rejectable.request.id)


@pytest.mark.parametrize(
    ("venue_id", "message"),
    [
        pytest.param(0, "suggested_venue_id must be a positive number.", id="zero"),
        pytest.param("2", "Not a valid integer.", id="a string"),
        pytest.param(True, "Not a valid integer.", id="a boolean"),
        pytest.param(1.5, "Not a valid integer.", id="a fraction"),
    ],
)
def test_a_suggested_venue_id_that_is_not_a_positive_whole_number_is_refused(
    db_session: Session, rejectable: Rejectable, venue_id: object, message: str
) -> None:
    details = _refusal(rejectable.request.id, db_session, suggested_venue_id=venue_id)

    assert details == {"suggested_venue_id": [message]}


# --------------------------------------------------------------------------
# AC1 — a replacement for an unavailable venue keeps its period (SCRUM-92)
# --------------------------------------------------------------------------


class Booked:
    """An event booked at the Auditorium; the Breakout and Garden rooms are free."""

    def __init__(
        self, event: EventRequest, original: VenueBookingRequest, venues: tuple[Venue, ...]
    ) -> None:
        self.event = event
        self.original = original
        self.auditorium, self.breakout, self.garden = venues


@pytest.fixture()
def booked(
    db_session: Session,
    saved_users: list[User],
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> Booked:
    auditorium, breakout = two_venues(make_venue, save)
    garden = make_venue(name="Garden room")
    save(garden)
    event = saved_event()
    original = decide(raise_booking(auditorium, event, db_session).id, "approved", db_session)
    return Booked(event, original, (auditorium, breakout, garden))


def _replace(booked: Booked, session: Session) -> VenueBookingRequest:
    """Replace the Auditorium booking with one at the Breakout room (SCRUM-92)."""
    return raise_booking(
        booked.breakout, booked.event, session, replaces_request_id=booked.original.id
    )


def test_a_replacement_for_an_unavailable_venue_may_not_be_given_another_period(
    db_session: Session, booked: Booked
) -> None:
    block(booked.auditorium, at(10), at(11), db_session)
    replacement = _replace(booked, db_session)

    details = _refusal(
        replacement.id, db_session, suggested_venue_id=booked.garden.id, **SUGGESTED_TIMES
    )

    assert details == {
        "suggested_starts_at": [PERIOD_LOCKED],
        "suggested_ends_at": [PERIOD_LOCKED],
    }
    assert reload_request(db_session, replacement.id).status is BookingRequestStatus.PENDING


def test_a_replacement_for_an_unavailable_venue_may_be_given_another_venue(
    db_session: Session, booked: Booked
) -> None:
    block(booked.auditorium, at(10), at(11), db_session)
    replacement = _replace(booked, db_session)

    rejected = _decide(replacement.id, db_session, suggested_venue_id=booked.garden.id)

    assert _suggestion(db_session, rejected.id) == (booked.garden.id, None, None)


def test_a_replacement_for_a_booking_flagged_after_a_change_may_be_given_another_period(
    db_session: Session, booked: Booked
) -> None:
    """Its venue is still there, so its replacement may move (ADR-0100)."""
    booked.original.reassessment_flags.append(
        ReassessmentFlag(kind=ReassessmentFlagKind.REQUIRES_RECONFIRMATION, reason="Moved.")
    )
    db_session.commit()
    replacement = _replace(booked, db_session)

    rejected = _decide(replacement.id, db_session, **SUGGESTED_TIMES)

    assert _suggestion(db_session, rejected.id) == (
        None,
        SUGGESTED_STARTS_UTC,
        SUGGESTED_ENDS_UTC,
    )


# --------------------------------------------------------------------------
# AC2 — the venue must be active; the period is checked only when it is used
# --------------------------------------------------------------------------


def test_an_inactive_venue_may_not_be_suggested(
    db_session: Session, rejectable: Rejectable
) -> None:
    rejectable.other.is_active = False
    db_session.commit()

    details = _refusal(rejectable.request.id, db_session, suggested_venue_id=rejectable.other.id)

    assert details == {"suggested_venue_id": [NOT_ACTIVE]}
    _assert_still_pending(db_session, rejectable.request.id)


def test_a_venue_that_does_not_exist_may_not_be_suggested(
    db_session: Session, rejectable: Rejectable
) -> None:
    details = _refusal(rejectable.request.id, db_session, suggested_venue_id=999)

    assert details == {"suggested_venue_id": [NOT_ACTIVE]}


def test_a_suggested_period_is_not_checked_against_the_venue_or_its_bookings(
    db_session: Session, booked: Booked
) -> None:
    """Outside the venue's hours and over its booking, a period is still suggested.

    SCRUM-42 checks all of that when the coordinator raises a request for it (AC2).
    """
    waiting = raise_booking(booked.breakout, booked.event, db_session)

    rejected = _decide(
        waiting.id,
        db_session,
        suggested_venue_id=booked.auditorium.id,
        suggested_starts_at=at(2).isoformat(),
        suggested_ends_at=at(11).isoformat(),
    )

    assert _suggestion(db_session, rejected.id) == (
        booked.auditorium.id,
        datetime(2026, 10, 31, 18, 0, tzinfo=UTC),
        datetime(2026, 11, 1, 3, 0, tzinfo=UTC),
    )


# --------------------------------------------------------------------------
# AC3 — the suggestion is on the request and in the decision's history entry
# --------------------------------------------------------------------------


def test_the_request_shows_the_suggestion_in_business_time(
    db_session: Session, rejectable: Rejectable
) -> None:
    rejected = _decide(
        rejectable.request.id,
        db_session,
        suggested_venue_id=rejectable.other.id,
        **SUGGESTED_TIMES,
    )
    shown = BookingRequestAsShown(
        request=rejected,
        proposed_date=date(2026, 11, 1),
        end_date=None,
        start_time=time(9, 0),
        end_time=time(17, 30),
        accessibility_needs=None,
    )

    body = VenueBookingRequestSchema().dump(shown)

    assert body["decision_reason"] == REASON
    assert body["suggested_venue_id"] == rejectable.other.id
    assert body["suggested_starts_at"] == "2026-11-03T14:00:00+08:00"
    assert body["suggested_ends_at"] == "2026-11-03T17:00:00+08:00"


def test_the_rejections_history_entry_records_the_suggestion_in_utc(
    db_session: Session, rejectable: Rejectable
) -> None:
    _decide(
        rejectable.request.id,
        db_session,
        suggested_venue_id=rejectable.other.id,
        **SUGGESTED_TIMES,
    )

    rejection = history_entries(db_session, rejectable.event.id)[-1]
    assert rejection.kind is EventHistoryKind.VENUE_BOOKING_REJECTED
    assert rejection.details["reason"] == REASON
    assert rejection.details["suggested_venue_id"] == rejectable.other.id
    assert rejection.details["suggested_starts_at"] == "2026-11-03T06:00:00+00:00"
    assert rejection.details["suggested_ends_at"] == "2026-11-03T09:00:00+00:00"


def test_a_suggested_venue_alone_is_recorded_without_a_period(
    db_session: Session, rejectable: Rejectable
) -> None:
    _decide(rejectable.request.id, db_session, suggested_venue_id=rejectable.other.id)

    details = history_entries(db_session, rejectable.event.id)[-1].details
    assert details["suggested_venue_id"] == rejectable.other.id
    assert "suggested_starts_at" not in details
    assert "suggested_ends_at" not in details


def test_a_suggested_period_alone_is_recorded_without_a_venue(
    db_session: Session, rejectable: Rejectable
) -> None:
    _decide(rejectable.request.id, db_session, **SUGGESTED_TIMES)

    details = history_entries(db_session, rejectable.event.id)[-1].details
    assert "suggested_venue_id" not in details
    assert details["suggested_starts_at"] == "2026-11-03T06:00:00+00:00"


def test_a_decision_with_no_suggestion_records_none(
    db_session: Session, rejectable: Rejectable
) -> None:
    """An approval's entry, or a bare rejection's, is as it was before SCRUM-70."""
    _decide(rejectable.request.id, db_session)

    details = history_entries(db_session, rejectable.event.id)[-1].details
    assert "suggested_venue_id" not in details
    assert "suggested_starts_at" not in details


def test_the_event_record_shows_the_suggested_venue_by_name_and_the_period(
    db_session: Session, rejectable: Rejectable
) -> None:
    """What the organiser and every staff reader see (SCRUM-24, ADR-0104)."""
    _decide(
        rejectable.request.id,
        db_session,
        suggested_venue_id=rejectable.other.id,
        **SUGGESTED_TIMES,
    )

    [shown] = services.list_every_arrangement_for_record(rejectable.event.id, session=db_session)

    assert shown.decision_reason == REASON
    assert shown.suggested_venue_name == "Breakout room"
    assert shown.suggested_starts_at == SUGGESTED_STARTS_UTC
    assert shown.suggested_ends_at == SUGGESTED_ENDS_UTC


def test_a_suggested_period_alone_shows_no_venue_on_the_record(
    db_session: Session, rejectable: Rejectable
) -> None:
    _decide(rejectable.request.id, db_session, **SUGGESTED_TIMES)

    [shown] = services.list_every_arrangement_for_record(rejectable.event.id, session=db_session)

    assert shown.suggested_venue_name is None
    assert shown.suggested_starts_at == SUGGESTED_STARTS_UTC


def test_the_records_arrangement_shows_the_suggestion_in_business_time(
    db_session: Session, rejectable: Rejectable
) -> None:
    _decide(
        rejectable.request.id,
        db_session,
        suggested_venue_id=rejectable.other.id,
        **SUGGESTED_TIMES,
    )
    [shown] = services.list_every_arrangement_for_record(rejectable.event.id, session=db_session)

    body = RecordVenueArrangementSchema().dump(shown)

    assert body["suggested_venue_name"] == "Breakout room"
    assert body["suggested_starts_at"] == "2026-11-03T14:00:00+08:00"
    assert body["suggested_ends_at"] == "2026-11-03T17:00:00+08:00"


# --------------------------------------------------------------------------
# AC4, AC5 — a new request is the coordinator's; the suggestion holds nothing
# --------------------------------------------------------------------------


def test_the_coordinator_raises_a_new_request_for_the_suggestion_and_the_rejected_one_stays(
    db_session: Session, rejectable: Rejectable
) -> None:
    """A resubmission counts as a new booking (customer FAQ); SCRUM-93 withdraws."""
    rejected = _decide(
        rejectable.request.id,
        db_session,
        suggested_venue_id=rejectable.other.id,
        **SUGGESTED_TIMES,
    )

    raised = raise_booking(rejectable.other, rejectable.event, db_session, **SUGGESTED_PERIOD)

    assert raised.id != rejected.id
    assert raised.status is BookingRequestStatus.PENDING
    assert (raised.venue_id, raised.starts_at) == (rejectable.other.id, SUGGESTED_STARTS_UTC)
    assert reload_request(db_session, rejected.id).status is BookingRequestStatus.REJECTED


def test_a_suggestion_books_and_holds_nothing(db_session: Session, rejectable: Rejectable) -> None:
    _decide(
        rejectable.request.id,
        db_session,
        suggested_venue_id=rejectable.other.id,
        **SUGGESTED_TIMES,
    )

    assert bookings(db_session) == []


def test_another_event_may_book_the_suggested_venue_for_the_suggested_period(
    db_session: Session, rejectable: Rejectable, saved_event: SavedEvent
) -> None:
    """Nothing was held for the coordinator the suggestion was for (AC5)."""
    _decide(
        rejectable.request.id,
        db_session,
        suggested_venue_id=rejectable.other.id,
        **SUGGESTED_TIMES,
    )
    other_event = raise_booking(rejectable.other, saved_event(), db_session, **SUGGESTED_PERIOD)

    approved = decide(other_event.id, "approved", db_session)

    assert approved.status is BookingRequestStatus.APPROVED


# --------------------------------------------------------------------------
# AC6 — the current coordinator is told once, by the rejection notice
# --------------------------------------------------------------------------

#: The other Event Coordinator ``saved_users`` saves, for an event reassigned to them.
OTHER_COORDINATOR_ID = 9
SUGGESTED_WHEN = "from 2026-11-03 14:00 to 2026-11-03 17:00"


def _decision_notices(session: Session) -> list[tuple[int, NotificationKind, str | None]]:
    """Each notice about a decision as (recipient, kind, detail), oldest first."""
    stmt = (
        select(Notification)
        .where(
            Notification.kind.in_(
                [NotificationKind.VENUE_BOOKING_APPROVED, NotificationKind.VENUE_BOOKING_REJECTED]
            )
        )
        .order_by(Notification.id)
    )
    notices = []
    for notice in session.scalars(stmt):
        notices.append((notice.recipient_id, notice.kind, notice.detail))
    return notices


def _rejection_notice(session: Session, rejectable: Rejectable, **suggestion: Any) -> str | None:
    """Reject with ``suggestion``; what the coordinator's one notice says."""
    _decide(rejectable.request.id, session, **suggestion)
    [(recipient, kind, detail)] = _decision_notices(session)
    assert (recipient, kind) == (COORDINATOR_ID, NotificationKind.VENUE_BOOKING_REJECTED)
    return detail


def test_the_notice_names_a_suggested_venue_and_period_before_the_reason(
    db_session: Session, rejectable: Rejectable
) -> None:
    detail = _rejection_notice(
        db_session, rejectable, suggested_venue_id=rejectable.other.id, **SUGGESTED_TIMES
    )

    assert detail == f"Suggested instead: Breakout room {SUGGESTED_WHEN}. Reason: {REASON}"


def test_the_notice_names_a_suggested_venue_for_the_same_period(
    db_session: Session, rejectable: Rejectable
) -> None:
    detail = _rejection_notice(db_session, rejectable, suggested_venue_id=rejectable.other.id)

    assert detail == f"Suggested instead: Breakout room for the same period. Reason: {REASON}"


def test_the_notice_names_a_suggested_period_at_the_same_venue(
    db_session: Session, rejectable: Rejectable
) -> None:
    detail = _rejection_notice(db_session, rejectable, **SUGGESTED_TIMES)

    assert detail == f"Suggested instead: the same venue {SUGGESTED_WHEN}. Reason: {REASON}"


def test_a_notice_with_no_suggestion_is_the_reason_alone(
    db_session: Session, rejectable: Rejectable
) -> None:
    assert _rejection_notice(db_session, rejectable) == REASON


def test_only_the_current_coordinator_is_told_of_the_suggestion(
    db_session: Session, rejectable: Rejectable
) -> None:
    """Reassigned after the request was raised: the new coordinator plans the event."""
    rejectable.event.coordinator_id = OTHER_COORDINATOR_ID
    db_session.commit()

    _decide(rejectable.request.id, db_session, suggested_venue_id=rejectable.other.id)

    assert _decision_notices(db_session) == [
        (
            OTHER_COORDINATOR_ID,
            NotificationKind.VENUE_BOOKING_REJECTED,
            f"Suggested instead: Breakout room for the same period. Reason: {REASON}",
        )
    ]
