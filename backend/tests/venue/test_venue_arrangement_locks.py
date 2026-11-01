"""Unit tests for SCRUM-93 — withdraw, change and cancel-all lock the arrangement row.

Venue Staff decide a request under a row lock (ADR-0045); the coordinator's actions on
the same row lock it too, so the two queue and the second sees what the first saved
(ADR-0118). SQLite ignores ``FOR UPDATE``: the lock is shown by the statement sent, and
the outcome of the race by a decision written underneath the session's cached copy,
as a decision committed while the coordinator's request was in flight would be.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.venue.conftest import (
    ARRANGEMENT_ACTIONS,
    ArrangementAction,
    SavedEvent,
    cancel_all_as_coordinator,
    change_purpose_as_coordinator,
    locked_request_reads,
    raise_booking,
    reload_request,
    set_status_underneath,
    withdraw_as_coordinator,
)

pytestmark = pytest.mark.scrum_93

WITHDRAW_REFUSAL = (
    "Only a pending, conflicting, held, rejected or expired arrangement can be withdrawn;"
    " this one is approved."
)
CHANGE_REFUSAL = "Only a pending arrangement can be changed; this one is approved."


@pytest.mark.parametrize("action", ARRANGEMENT_ACTIONS)
def test_the_arrangement_is_read_under_a_row_lock(
    db_session: Session, venue: Venue, saved_event: SavedEvent, action: ArrangementAction
) -> None:
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)

    reads = locked_request_reads(db_session, lambda: action(event, arrangement.id, db_session))

    assert len(reads) == 1


@pytest.mark.parametrize(
    ("action", "refusal"),
    [
        pytest.param(withdraw_as_coordinator, WITHDRAW_REFUSAL, id="withdraw"),
        pytest.param(change_purpose_as_coordinator, CHANGE_REFUSAL, id="change"),
    ],
)
def test_an_approval_saved_meanwhile_is_seen_and_refuses_the_action(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    action: ArrangementAction,
    refusal: str,
) -> None:
    """Without the locked read, the stale Pending copy would be withdrawn or changed.

    Cancel-all, which cancels an approved booking rather than refusing, is below.
    """
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)
    set_status_underneath(arrangement, BookingRequestStatus.APPROVED, db_session)

    with pytest.raises(ConflictError) as caught:
        action(event, arrangement.id, db_session)

    assert caught.value.message == refusal
    db_session.commit()
    kept = reload_request(db_session, arrangement.id)
    assert (kept.status, kept.purpose) == (BookingRequestStatus.APPROVED, "Main hall")


def test_cancel_all_sees_an_approval_saved_meanwhile_and_cancels_the_booking(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """Without the locked read, the stale Pending copy would be withdrawn instead."""
    event = saved_event()
    arrangement = raise_booking(venue, event, db_session)
    set_status_underneath(arrangement, BookingRequestStatus.APPROVED, db_session)

    cancel_all_as_coordinator(event, arrangement.id, db_session)

    assert reload_request(db_session, arrangement.id).status is BookingRequestStatus.CANCELLED
