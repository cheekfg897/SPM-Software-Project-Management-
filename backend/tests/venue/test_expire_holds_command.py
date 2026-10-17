"""Unit tests for SCRUM-94 — the ``flask expire-holds`` command.

The scheduled workflow runs it (ADR-0052): it expires the holds that have run out, then
warns about the ones expiring within 24 hours, and says how many of each.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from click.testing import Result
from flask import Flask
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, VenueBookingRequest
from tests.venue.conftest import hours_from_now, place_hold

pytestmark = pytest.mark.scrum_94


def _run(app: Flask) -> Result:
    """Run ``flask expire-holds``."""
    return app.test_cli_runner().invoke(args=["expire-holds"])


def _statuses(event: EventRequest, session: Session) -> list[BookingRequestStatus]:
    """The statuses of the event's two requests, earlier period first."""
    session.expire_all()
    return [
        request.status for request in services.list_active_arrangements(event.id, session=session)
    ]


def test_the_command_expires_the_holds_that_ran_out_and_warns_about_those_near_expiry(
    app: Flask,
    db_session: Session,
    multi_venue_event: EventRequest,
    multi_venue_request: VenueBookingRequest,
    pin_now: Callable[[datetime], None],
) -> None:
    """The first hold has run out; the second expires in an hour, so is warned about."""
    first_expiry = hours_from_now(48)
    second = services.list_active_arrangements(multi_venue_event.id, session=db_session)[1]
    place_hold(multi_venue_request.id, first_expiry, db_session)
    place_hold(second.id, first_expiry + timedelta(hours=2), db_session)
    pin_now(first_expiry + timedelta(hours=1))

    result = _run(app)

    assert result.exit_code == 0, result.output
    assert result.output == "Expired 1 hold(s); warned about 1 hold(s).\n"
    assert _statuses(multi_venue_event, db_session) == [
        BookingRequestStatus.EXPIRED,
        BookingRequestStatus.ON_HOLD,
    ]


def test_the_command_with_nothing_due_changes_nothing(
    app: Flask,
    db_session: Session,
    multi_venue_event: EventRequest,
    multi_venue_request: VenueBookingRequest,
) -> None:
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)

    result = _run(app)

    assert result.exit_code == 0, result.output
    assert result.output == "Expired 0 hold(s); warned about 0 hold(s).\n"
    assert _statuses(multi_venue_event, db_session) == [
        BookingRequestStatus.ON_HOLD,
        BookingRequestStatus.PENDING,
    ]
