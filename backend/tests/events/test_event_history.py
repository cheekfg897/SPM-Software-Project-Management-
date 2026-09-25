"""Unit tests for the event history table SCRUM-30 introduces (ADR-0018).

One table records what happens to an event request; assignment (SCRUM-30) is its first
writer. ``record_event_history`` adds an entry to the caller's session without
committing, so the entry is saved with the change it records or not at all, even when
the request itself hasn't been flushed yet.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventHistoryEntry, EventHistoryKind, EventRequest
from app.modules.events.services import record_event_history

pytestmark = pytest.mark.scrum_30

MakeEventRequest = Callable[..., EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]

OCCURRED_AT = datetime(2026, 9, 15, 2, 30, tzinfo=timezone.utc)


def _reloaded(db_session: Session, entry: EventHistoryEntry) -> EventHistoryEntry:
    """``entry`` as the database has it, not as the session remembers it."""
    db_session.expire_all()
    reloaded = db_session.get(EventHistoryEntry, entry.id)
    assert reloaded is not None
    return reloaded


def test_an_entry_is_added_to_the_session_without_committing(
    mock_session: MagicMock, make_event_request: MakeEventRequest
) -> None:
    entry = record_event_history(
        make_event_request(),
        EventHistoryKind.COORDINATOR_ASSIGNED,
        actor_id=None,
        details={"coordinator_id": 3},
        session=mock_session,
        now=OCCURRED_AT,
    )

    mock_session.add.assert_called_once_with(entry)
    mock_session.commit.assert_not_called()
    assert (entry.kind, entry.actor_id, entry.details, entry.occurred_at) == (
        EventHistoryKind.COORDINATOR_ASSIGNED,
        None,
        {"coordinator_id": 3},
        OCCURRED_AT,
    )


def test_an_entry_can_be_attached_before_the_request_is_saved(
    db_session: Session, make_event_request: MakeEventRequest, history_of: HistoryOf
) -> None:
    event_request = make_event_request()
    db_session.add(event_request)  # not flushed: the request has no id yet

    record_event_history(
        event_request,
        EventHistoryKind.COORDINATOR_ASSIGNED,
        actor_id=None,
        details={"coordinator_id": 3},
        session=db_session,
        now=OCCURRED_AT,
    )
    db_session.commit()

    assert history_of(event_request.id) == [
        (EventHistoryKind.COORDINATOR_ASSIGNED, None, {"coordinator_id": 3})
    ]


def test_an_entry_is_saved_with_kind_actor_details_and_time(
    db_session: Session, save: Callable[..., None], make_event_request: MakeEventRequest
) -> None:
    event_request = make_event_request()
    save(event_request)

    entry = record_event_history(
        event_request,
        EventHistoryKind.COORDINATOR_ASSIGNED,
        actor_id=3,
        session=db_session,
        now=OCCURRED_AT,
    )
    db_session.commit()

    reloaded = _reloaded(db_session, entry)
    assert (
        reloaded.event_request_id,
        reloaded.kind,
        reloaded.actor_id,
        reloaded.details,
        reloaded.occurred_at,
    ) == (event_request.id, EventHistoryKind.COORDINATOR_ASSIGNED, 3, None, OCCURRED_AT)


def test_occurred_at_defaults_to_the_current_instant(
    db_session: Session, save: Callable[..., None], make_event_request: MakeEventRequest
) -> None:
    event_request = make_event_request()
    save(event_request)
    before = datetime.now(timezone.utc)

    entry = record_event_history(
        event_request, EventHistoryKind.COORDINATOR_ASSIGNED, actor_id=None, session=db_session
    )
    db_session.commit()

    after = datetime.now(timezone.utc)
    assert before <= _reloaded(db_session, entry).occurred_at <= after
