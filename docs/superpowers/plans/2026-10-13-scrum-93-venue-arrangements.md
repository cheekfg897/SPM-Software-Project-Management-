# SCRUM-93 Venue Arrangements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a coordinator retire and change one of an event's venue arrangements without disturbing the others, and expose the "active arrangement" seam that SCRUM-75, SCRUM-49 and SCRUM-97 are blocked on.

**Architecture:** An arrangement is the existing `VenueBookingRequest` row — no new table. A new `withdrawn` status retires one; `RETIRED_REQUEST_STATUSES` is the exclusion set that defines "active", phrased so later statuses stay active by default. All new behaviour lives in `app/modules/venue/services.py` behind thin routes, with history entries written through `app/modules/events/services.py` so the venue module never imports the events models.

**Tech Stack:** Python 3.13, Flask, SQLAlchemy 2 (`Mapped`/`mapped_column`), marshmallow, Alembic, pytest. Unit suite only: no Postgres, no Flask test client.

**Spec:** `docs/superpowers/specs/2026-10-13-scrum-93-venue-arrangements-design.md` — read it first; it carries the reasoning and the deferred-AC owners.

## Global Constraints

- **British spelling** in code and API: `organiser`, `normalise`, `serialise`, `cancelled`, `withdrawn`.
- **Module boundaries.** `app/modules/venue/` must never import `app.modules.events.models`. It calls `app.modules.events.services` functions, imported **inside the function body** (`from app.modules.events import services as event_services`) because events → equipment → venue already, per ADR-0035 §9.
- **Layers.** `routes.py` is thin: parse JSON → call service → serialise. Services raise `AppError` subclasses from `app.common.errors`; routes never build error responses.
- **Service signatures** take keyword-only `session: Session | None = None` and resolve it with `resolve_session(session)`.
- **Dates:** never `date.today()` or naive `datetime.now()` — ruff DTZ blocks them.
- **Helpers first:** in every file, a helper sits **above** the functions that use it.
- **No repeated code**, in tests too. Extract on the second real use.
- **Every test module** sets `pytestmark = pytest.mark.scrum_93`.
- **One Alembic head.** This branch adds exactly one migration, `0023`, chained on `0022_add_lead_role`.
- **Commit subjects** are Conventional Commits naming the story: `feat(SCRUM-93): ...`. **Never add `Co-Authored-By` or any AI attribution line to a commit or PR.**
- Run everything from `backend/`. This worktree has no venv of its own, so use the main checkout's. Export this once per shell; every command below writes `$PY`:

```bash
export PY=/Users/ernesttan/Desktop/SMU/Y3S1/SPM/SPM-Software-Project-Management-/backend/.venv/bin/python
cd /Users/ernesttan/Desktop/SMU/Y3S1/SPM/spm-worktrees/SCRUM-93/backend
```

`ruff` and `diff-cover` live beside it, so `$PY -m ruff` and `$PY -m diff-cover` both work.

## Review Focus

Input classes the spec implies but no task's own happy path exercises. Each has its test added to the task that owns the code.

1. **Withdrawing an arrangement that is already withdrawn** — must be a 409 naming the status, not a silent second withdrawal. (Task 2)
2. **An arrangement id belonging to a different event** — must be 404, not a cross-event withdrawal. (Task 2)
3. **`cancel-all` on an event with no arrangements** — must return `[]` and commit nothing, not fail. (Task 3)
4. **A change that makes the venue unsuitable with no justification** — must be refused *and* leave the stored row untouched, including when a later field in the same payload was valid. (Task 4)
5. **Re-raising the same venue and period after withdrawing** — must succeed, because `uq_venue_booking_requests_pending` covers `status = 'pending'` only. (Task 5)

---

### Task 1: The `withdrawn` status, the active-arrangement seam, migration 0023

**Files:**
- Modify: `backend/app/modules/venue/models.py` (`BookingRequestStatus`, add `RETIRED_REQUEST_STATUSES` below it)
- Modify: `backend/app/modules/events/models.py` (`EventHistoryKind`: two new members)
- Modify: `backend/app/modules/venue/services.py` (append a new SCRUM-93 section at the end)
- Create: `backend/migrations/versions/0023_add_withdrawn_arrangements.py`
- Modify: `backend/pytest.ini` (declare the `scrum_93` marker)
- Test: `backend/tests/venue/test_venue_arrangements.py`

**Interfaces:**
- Consumes: `VenueBookingRequest`, `BookingRequestStatus` from `app.modules.venue.models`; `resolve_session` from `app.common.database`.
- Produces: `BookingRequestStatus.WITHDRAWN`; `RETIRED_REQUEST_STATUSES: frozenset[BookingRequestStatus]`; `list_active_arrangements(event_id: int, *, session: Session | None = None) -> list[VenueBookingRequest]`; `count_active_arrangements(event_id: int, *, session: Session | None = None) -> int`; `EventHistoryKind.VENUE_ARRANGEMENT_WITHDRAWN`, `EventHistoryKind.VENUE_ARRANGEMENT_CHANGED`.

- [ ] **Step 1: Declare the marker**

In `backend/pytest.ini`, add this line to the `markers` block, directly after the `scrum_95` line and before the `e2e` line (markers are `--strict-markers`, so an undeclared one errors):

```
    scrum_93: tests for SCRUM-93 "book several venues for one event"
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/venue/test_venue_arrangements.py`:

```python
"""Unit tests for SCRUM-93 — several venue arrangements for one event.

An arrangement is a ``VenueBookingRequest``. This file covers retiring one and the
"active arrangement" seam that SCRUM-75 counts to decide whether an event is
multi-venue (AC5, AC6).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.venue.conftest import COORDINATOR_ID, SavedEvent, raise_booking

pytestmark = pytest.mark.scrum_93

SECOND_PERIOD = {
    "starts_at": "2026-11-01T13:00:00+08:00",
    "ends_at": "2026-11-01T16:00:00+08:00",
}


def _two_arrangements(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    event: EventRequest,
) -> tuple[int, int]:
    """Raise one arrangement at each of two venues; return their ids in order."""
    auditorium = make_venue(name="Auditorium")
    breakout = make_venue(name="Breakout room")
    save(auditorium)
    save(breakout)
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
    event = saved_event()
    first_id, second_id = _two_arrangements(db_session, make_venue, save, event)

    active = services.list_active_arrangements(event.id, session=db_session)

    assert [arrangement.id for arrangement in active] == [first_id, second_id]


def test_another_events_arrangements_are_not_counted(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    mine = saved_event()
    theirs = saved_event()
    raise_booking(venue, theirs, db_session)

    assert services.count_active_arrangements(mine.id, session=db_session) == 0
```

Note: `services.VenueBookingRequest` is the model re-exported through the service module's own import — it is already imported there, so this works and keeps the test from importing the model directly.

- [ ] **Step 3: Run the test to verify it fails**

Run: `$PY -m pytest tests/venue/test_venue_arrangements.py -q`
Expected: FAIL — `AttributeError: WITHDRAWN` on `BookingRequestStatus`, and `AttributeError: module 'app.modules.venue.services' has no attribute 'count_active_arrangements'`.

- [ ] **Step 4: Add the status and the exclusion set**

In `backend/app/modules/venue/models.py`, replace the `BookingRequestStatus` class with:

```python
class BookingRequestStatus(str, enum.Enum):
    """Where a venue booking request stands (SCRUM-42, SCRUM-93).

    ``PENDING`` and ``WITHDRAWN`` exist so far; SCRUM-43 adds approving, rejecting
    and cancelling, and SCRUM-75 adds holding.
    """

    PENDING = "pending"
    #: The coordinator retracted the arrangement before Venue Staff decided it
    #: (SCRUM-93 AC6). The row stays so SCRUM-75 can ignore it when counting venues.
    WITHDRAWN = "withdrawn"


#: Statuses that take an arrangement out of an event's venue count (SCRUM-93).
#: SCRUM-43 adds ``CANCELLED`` and ``REJECTED`` here; ``ON_HOLD`` must stay out, because
#: SCRUM-75 treats a held arrangement as one of the event's active venues.
RETIRED_REQUEST_STATUSES = frozenset({BookingRequestStatus.WITHDRAWN})
```

- [ ] **Step 5: Add the two history kinds**

In `backend/app/modules/events/models.py`, append to `EventHistoryKind`, directly after the `EQUIPMENT_RESERVED` member:

```python
    #: The assigned coordinator changed one of the event's venue arrangements;
    #: ``details`` holds ``venue_booking_request_id``, ``venue_id`` and each changed
    #: field with its ``previous`` and ``new`` value (SCRUM-93 AC6).
    VENUE_ARRANGEMENT_CHANGED = "venue_arrangement_changed"
    #: The assigned coordinator withdrew one of the event's venue arrangements before
    #: Venue Staff decided it; ``details`` holds ``venue_booking_request_id`` and
    #: ``venue_id`` (SCRUM-93 AC6).
    VENUE_ARRANGEMENT_WITHDRAWN = "venue_arrangement_withdrawn"
```

- [ ] **Step 6: Add the active-arrangement seam**

Append to the **end** of `backend/app/modules/venue/services.py`:

```python
# --------------------------------------------------------------------------
# SCRUM-93 — several venue arrangements for one event
# --------------------------------------------------------------------------


def list_active_arrangements(
    event_id: int, *, session: Session | None = None
) -> list[VenueBookingRequest]:
    """The event's arrangements that still count towards its venues (AC5).

    Retired ones are left out, so SCRUM-75 can ask whether an event has more than one
    venue. Earliest period first, as the event's own list of requests is.
    """
    query = (
        select(VenueBookingRequest)
        .where(
            VenueBookingRequest.event_id == event_id,
            VenueBookingRequest.status.not_in(RETIRED_REQUEST_STATUSES),
        )
        .order_by(VenueBookingRequest.starts_at, VenueBookingRequest.id)
    )
    return list(resolve_session(session).scalars(query).all())


def count_active_arrangements(event_id: int, *, session: Session | None = None) -> int:
    """How many venues the event still has arranged (SCRUM-75's multi-venue test)."""
    return len(list_active_arrangements(event_id, session=session))
```

Add `RETIRED_REQUEST_STATUSES` to the existing `from app.modules.venue.models import (...)` block, in alphabetical position (after `RequirementKind`).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `$PY -m pytest tests/venue/test_venue_arrangements.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 8: Write migration 0023**

Create `backend/migrations/versions/0023_add_withdrawn_arrangements.py`. This follows `0022_add_lead_role.py` exactly — read that file first. It is not covered by the unit suite (there is no Postgres); CI replays downgrade → upgrade, so the downgrade must rebuild both enum types.

```python
"""Add the withdrawn arrangement status and the arrangement history kinds.

Revision ID: 0023_add_withdrawn_arrangements
Revises: 0022_add_lead_role
Create Date: 2026-10-13

SCRUM-93 "Book several venues for one event" (ADR-0039):

* ``booking_request_status`` gains ``withdrawn``, so a coordinator can retire one of an
  event's arrangements without disturbing the others (AC6).
* ``event_history_entry_kind`` gains ``venue_arrangement_changed`` and
  ``venue_arrangement_withdrawn``, the audit entries for those actions.

``cancelled`` is deliberately **not** added: nothing can produce it until SCRUM-43 gives
an arrangement an ``approved`` status to be cancelled from.

Values are added outside the migration's transaction, with ``IF NOT EXISTS``, as 0019
and 0022 do. Downgrading rebuilds both enum types without the new values (lossy): a
withdrawn arrangement goes back to ``pending`` and the new history entries are deleted.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0023_add_withdrawn_arrangements"
down_revision = "0022_add_lead_role"
branch_labels = None
depends_on = None

#: What migration 0020 created. Downgrade rebuilds ``booking_request_status`` with this.
PREVIOUS_REQUEST_STATUS_VALUES = ("pending",)

#: Added here (SCRUM-93 AC6).
ADDED_REQUEST_STATUS_VALUES = ("withdrawn",)

#: What migrations 0009-0021 left. Downgrade rebuilds ``event_history_entry_kind``
#: with just this.
PREVIOUS_HISTORY_KIND_VALUES = (
    "coordinator_assigned",
    "coordinator_reassigned",
    "field_changed",
    "event_completed",
    "review_started",
    "decision_recorded",
    "clarification_requested",
    "clarification_answered",
    # Added below us in the stack: 0020 (SCRUM-42) and 0021 (SCRUM-46).
    "venue_booking_requested",
    "equipment_reserved",
)

#: Added here (the audit entries for changing and withdrawing an arrangement).
ADDED_HISTORY_KIND_VALUES = ("venue_arrangement_changed", "venue_arrangement_withdrawn")


def _add_enum_values(type_name: str, values: tuple[str, ...]) -> None:
    for value in values:
        op.execute(
            sa.text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS :value").bindparams(
                value=value
            )
        )


def _rebuild_enum_without_added_values(
    type_name: str, table: str, column: str, previous_values: tuple[str, ...]
) -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the column re-cast.
    op.execute(sa.text(f"ALTER TYPE {type_name} RENAME TO {type_name}_old"))
    sa.Enum(*previous_values, name=type_name).create(op.get_bind())
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE {type_name} USING {column}::text::{type_name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {type_name}_old"))


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("booking_request_status", ADDED_REQUEST_STATUS_VALUES)
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)


def downgrade() -> None:
    # A withdrawn arrangement goes back to the status it was withdrawn from, and the
    # new history entries are deleted, before each type is rebuilt.
    op.execute(
        sa.text("UPDATE venue_booking_requests SET status = 'pending' WHERE status = 'withdrawn'")
    )
    _rebuild_enum_without_added_values(
        "booking_request_status",
        "venue_booking_requests",
        "status",
        PREVIOUS_REQUEST_STATUS_VALUES,
    )
    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    _rebuild_enum_without_added_values(
        "event_history_entry_kind",
        "event_history_entries",
        "kind",
        PREVIOUS_HISTORY_KIND_VALUES,
    )
```

- [ ] **Step 9: Check lint, the whole suite and the single head**

Run, in order:

```bash
$PY -m ruff format .
$PY -m ruff check .
$PY -m pytest -q
```

Expected: formatted, `All checks passed!`, and every test passing (the suite was green before this task, so a failure here is yours). `flask db heads` needs a database and cannot run in this worktree; instead confirm by eye that `0023_add_withdrawn_arrangements.py` is the only file whose `down_revision` is `"0022_add_lead_role"`:

```bash
grep -rn "down_revision" migrations/versions/ | grep 0022_add_lead_role
```

Expected: exactly one line.

- [ ] **Step 10: Commit**

```bash
git add backend/pytest.ini backend/app/modules/venue/models.py backend/app/modules/events/models.py backend/app/modules/venue/services.py backend/migrations/versions/0023_add_withdrawn_arrangements.py backend/tests/venue/test_venue_arrangements.py
git commit -m "feat(SCRUM-93): count an event's active venue arrangements"
```

---

### Task 2: Withdraw one arrangement

**Files:**
- Modify: `backend/app/modules/events/services.py` (a recorder beside `record_venue_booking_requested`, around line 1034)
- Modify: `backend/app/modules/venue/services.py` (the SCRUM-93 section)
- Modify: `backend/app/modules/venue/routes.py` (after `list_booking_requests`)
- Test: `backend/tests/venue/test_venue_arrangements.py` (append), `backend/tests/venue/test_venue_permissions.py` (append)

**Interfaces:**
- Consumes: `list_active_arrangements`, `RETIRED_REQUEST_STATUSES`, `BookingRequestStatus.WITHDRAWN`, `EventHistoryKind.VENUE_ARRANGEMENT_WITHDRAWN` from Task 1; `show_booking_request(request, event) -> BookingRequestAsShown` and `BookingRequestAsShown` from SCRUM-42; `event_services.get_event_for_coordinator(reference, coordinator_id, *, session)` returning `EventForBooking` (has `.id`).
- Produces: `event_services.record_venue_arrangement_withdrawn(event_id, *, actor_id, details, session=None) -> EventHistoryEntry`; `venue.services._arrangement_of_event(event_id, arrangement_id, session) -> VenueBookingRequest`; `venue.services._withdraw_and_record(arrangement, coordinator_id, session) -> None`; `venue.services.withdraw_arrangement(reference, arrangement_id, *, coordinator_id, session=None) -> BookingRequestAsShown`; `ARRANGEMENT_NOT_FOUND_MESSAGE`, `WITHDRAW_NOT_PENDING_MESSAGE`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/venue/test_venue_arrangements.py`. Add `ConflictError` and `NotFoundError` to the `from app.common.errors import ...` line (create the import if the file has none yet), and add `EventHistoryEntry, EventHistoryKind` to the existing `from app.modules.events.models import ...` line.

```python
def _history(session: Session) -> list[EventHistoryEntry]:
    return session.query(EventHistoryEntry).all()


def _withdraw(event: EventRequest, arrangement_id: int, session: Session) -> object:
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest tests/venue/test_venue_arrangements.py -q`
Expected: FAIL — `module 'app.modules.venue.services' has no attribute 'withdraw_arrangement'`.

- [ ] **Step 3: Add the history recorder**

In `backend/app/modules/events/services.py`, directly **below** `record_venue_booking_requested` (it ends around line 1053):

```python
def record_venue_arrangement_withdrawn(
    event_id: int,
    *,
    actor_id: int,
    details: dict[str, Any],
    session: Session | None = None,
) -> EventHistoryEntry:
    """Add the history entry for a withdrawn arrangement, without committing (SCRUM-93).

    The entry rides in the caller's transaction, so it is saved with the withdrawal it
    records or not at all (ADR-0018).
    """
    event_request = resolve_session(session).get(EventRequest, event_id)
    return record_event_history(
        event_request,
        EventHistoryKind.VENUE_ARRANGEMENT_WITHDRAWN,
        actor_id=actor_id,
        details=details,
        session=session,
    )
```

- [ ] **Step 4: Add the service**

In the SCRUM-93 section of `backend/app/modules/venue/services.py`, **above** `list_active_arrangements` put the two messages, and below `count_active_arrangements` put the helpers and the public function (helpers first within their own group):

```python
ARRANGEMENT_NOT_FOUND_MESSAGE = "Venue arrangement not found."
WITHDRAW_NOT_PENDING_MESSAGE = (
    "Only a pending arrangement can be withdrawn; this one is {status}."
)
```

```python
def _arrangement_of_event(
    event_id: int, arrangement_id: int, session: Session
) -> VenueBookingRequest:
    """One of the event's own arrangements.

    An id that belongs to another event is reported as missing, so arrangements of
    events the caller cannot see are not discoverable (ADR-0035 §6).

    Raises:
        NotFoundError: 404 — the event has no arrangement with that id.
    """
    arrangement = session.get(VenueBookingRequest, arrangement_id)
    if arrangement is None or arrangement.event_id != event_id:
        raise NotFoundError(ARRANGEMENT_NOT_FOUND_MESSAGE)
    return arrangement


def _withdraw_and_record(
    arrangement: VenueBookingRequest, coordinator_id: int, session: Session | None
) -> None:
    """Withdraw one arrangement and write its history entry, without committing.

    Raises:
        ConflictError: 409 — the arrangement is no longer pending.
    """
    from app.modules.events import services as event_services  # circular at import time

    if arrangement.status is not BookingRequestStatus.PENDING:
        raise ConflictError(
            WITHDRAW_NOT_PENDING_MESSAGE.format(status=arrangement.status.value)
        )
    arrangement.status = BookingRequestStatus.WITHDRAWN
    event_services.record_venue_arrangement_withdrawn(
        arrangement.event_id,
        actor_id=coordinator_id,
        details={
            "venue_booking_request_id": arrangement.id,
            "venue_id": arrangement.venue_id,
        },
        session=session,
    )


def withdraw_arrangement(
    reference: str,
    arrangement_id: int,
    *,
    coordinator_id: int,
    session: Session | None = None,
) -> BookingRequestAsShown:
    """Retract one of an event's arrangements before Venue Staff decide it (AC6).

    The event's other arrangements are untouched. The withdrawal and its history entry
    are saved in one commit.

    Raises:
        NotFoundError: 404 — no such event among the coordinator's own, or no such
            arrangement on it.
        ConflictError: 409 — the arrangement is no longer pending.
    """
    from app.modules.events import services as event_services  # circular at import time

    sess = resolve_session(session)
    event = event_services.get_event_for_coordinator(reference, coordinator_id, session=session)
    arrangement = _arrangement_of_event(event.id, arrangement_id, sess)
    _withdraw_and_record(arrangement, coordinator_id, session)
    sess.commit()
    return show_booking_request(arrangement, event)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `$PY -m pytest tests/venue/test_venue_arrangements.py -q`
Expected: PASS, 12 tests.

- [ ] **Step 6: Add the route**

In `backend/app/modules/venue/routes.py`, after `list_booking_requests`:

```python
@bp.post("/events/<reference>/booking-requests/<int:arrangement_id>/withdraw")
@requires_role(Role.EVENT_COORDINATOR)
def withdraw_arrangement(reference: str, arrangement_id: int) -> tuple[Response, int]:
    """Retract one of the coordinator's event's venue arrangements."""
    shown = services.withdraw_arrangement(
        reference, arrangement_id, coordinator_id=int(g.current_user_id)
    )
    return jsonify(_booking_request_schema.dump(shown)), 200
```

- [ ] **Step 7: Add the permission test**

Open `backend/tests/venue/test_venue_permissions.py`, read how it parametrises the existing booking-request routes, and add a case for `venue.withdraw_arrangement` in exactly that style — Event Coordinator allowed, every other role refused. Do not invent a new pattern; match the file.

- [ ] **Step 8: Run lint and the whole suite**

```bash
$PY -m ruff format . && $PY -m ruff check . && $PY -m pytest -q
```

Expected: formatted, `All checks passed!`, everything passing.

- [ ] **Step 9: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat(SCRUM-93): withdraw one of an event's venue arrangements"
```

---

### Task 3: Retire every arrangement at once

**Files:**
- Modify: `backend/app/modules/venue/services.py` (SCRUM-93 section)
- Modify: `backend/app/modules/venue/routes.py`
- Test: `backend/tests/venue/test_venue_arrangements.py` (append), `backend/tests/venue/test_venue_permissions.py` (append)

**Interfaces:**
- Consumes: `list_active_arrangements`, `_withdraw_and_record`, `show_booking_request` from Tasks 1-2.
- Produces: `venue.services.cancel_all_arrangements(reference, *, coordinator_id, session=None) -> list[BookingRequestAsShown]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/venue/test_venue_arrangements.py`:

```python
def _cancel_all(event: EventRequest, session: Session) -> list[object]:
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PY -m pytest tests/venue/test_venue_arrangements.py -q`
Expected: FAIL — no attribute `cancel_all_arrangements`.

- [ ] **Step 3: Write the service**

Append to the SCRUM-93 section of `backend/app/modules/venue/services.py`:

```python
def cancel_all_arrangements(
    reference: str, *, coordinator_id: int, session: Session | None = None
) -> list[BookingRequestAsShown]:
    """Retire every arrangement the event still has (AC6's explicit "cancel all").

    AC6 keeps one arrangement's fate from touching the others unless the coordinator
    asks for all of them, which is this call rather than a loop the client writes.
    Every active arrangement is pending today, so each is withdrawn; SCRUM-43 adds
    cancelling the approved ones. An event with none is not an error.

    Returns:
        The retired arrangements, earliest period first, or an empty list.

    Raises:
        NotFoundError: 404 — no such event among the coordinator's own.
    """
    from app.modules.events import services as event_services  # circular at import time

    sess = resolve_session(session)
    event = event_services.get_event_for_coordinator(reference, coordinator_id, session=session)
    arrangements = list_active_arrangements(event.id, session=session)
    for arrangement in arrangements:
        _withdraw_and_record(arrangement, coordinator_id, session)
    sess.commit()
    return [show_booking_request(arrangement, event) for arrangement in arrangements]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$PY -m pytest tests/venue/test_venue_arrangements.py -q`
Expected: PASS, 16 tests.

- [ ] **Step 5: Add the route**

In `backend/app/modules/venue/routes.py`, after the withdraw route:

```python
@bp.post("/events/<reference>/booking-requests/cancel-all")
@requires_role(Role.EVENT_COORDINATOR)
def cancel_all_arrangements(reference: str) -> tuple[Response, int]:
    """Retire every venue arrangement the coordinator's event still has."""
    shown = services.cancel_all_arrangements(reference, coordinator_id=int(g.current_user_id))
    return jsonify(_booking_request_schema.dump(shown, many=True)), 200
```

- [ ] **Step 6: Add the permission test**

Add a `venue.cancel_all_arrangements` case to `backend/tests/venue/test_venue_permissions.py`, in the file's existing style.

- [ ] **Step 7: Run lint and the whole suite**

```bash
$PY -m ruff format . && $PY -m ruff check . && $PY -m pytest -q
```

- [ ] **Step 8: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat(SCRUM-93): retire every venue arrangement on one request"
```

---

### Task 4: Change a pending arrangement

**Files:**
- Modify: `backend/app/modules/events/services.py` (a second recorder)
- Modify: `backend/app/modules/venue/schemas.py` (a new schema beside `RaiseBookingRequestSchema`, around line 404)
- Modify: `backend/app/modules/venue/services.py` (SCRUM-93 section)
- Modify: `backend/app/modules/venue/routes.py`
- Test: Create `backend/tests/venue/test_venue_arrangement_changes.py`; append to `backend/tests/venue/test_venue_permissions.py`

**Interfaces:**
- Consumes: `_arrangement_of_event` (Task 2), `_venue_is_suitable`, `JUSTIFICATION_REQUIRED_MESSAGE`, `show_booking_request`, `load_or_raise`; `EventHistoryKind.VENUE_ARRANGEMENT_CHANGED` (Task 1).
- Produces: `ChangeArrangementSchema`; `event_services.record_venue_arrangement_changed(...)`; `venue.services.change_arrangement(reference, arrangement_id, payload, *, coordinator_id, session=None) -> BookingRequestAsShown`; `CHANGE_NOT_PENDING_MESSAGE`, `CHANGEABLE_FIELDS`.

- [ ] **Step 1: Read the schema you are copying**

Open `backend/app/modules/venue/schemas.py` and read `RaiseBookingRequestSchema` in full (around line 404), including the validators it uses (`not_blank`, the `LayoutType` `OneOf`, the occupancy `Range`). The new schema reuses the same field definitions with nothing required, and **omits `venue_id`, `starts_at` and `ends_at`** — the venue and period do not move (see the spec, §5).

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/venue/test_venue_arrangement_changes.py`:

```python
"""Unit tests for SCRUM-93 AC6 — changing one of an event's venue arrangements.

Only a pending arrangement changes, and only its purpose, occupancy, layout and
justification: the venue and period are the slot Venue Staff were asked about, so moving
either means withdrawing this arrangement and raising another.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.events.models import EventHistoryEntry, EventHistoryKind, EventRequest
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.venue.conftest import COORDINATOR_ID, SavedEvent, raise_booking

pytestmark = pytest.mark.scrum_93

UNSUITABLE_MESSAGE = "A justification is required because the venue is not suitable."


def _change(
    event: EventRequest, arrangement_id: int, session: Session, **fields: Any
) -> object:
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


def test_raising_the_occupancy_past_the_venues_capacity_needs_a_justification(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """Review Focus 4: the refusal must also leave the stored row untouched."""
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
    db_session.expire_all()
    unchanged = db_session.get(services.VenueBookingRequest, arrangement.id)
    assert unchanged is not None
    assert unchanged.expected_occupancy == 50
    assert unchanged.purpose == "Main hall"


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

    shown = _change(
        event, arrangement.id, db_session, expected_occupancy=venue.capacity + 6
    )

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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `$PY -m pytest tests/venue/test_venue_arrangement_changes.py -q`
Expected: FAIL — no attribute `change_arrangement`.

- [ ] **Step 4: Add the schema**

In `backend/app/modules/venue/schemas.py`, directly below `RaiseBookingRequestSchema`:

```python
class ChangeArrangementSchema(Schema):
    """Payload for ``PATCH`` on one of an event's arrangements (SCRUM-93 AC6).

    Every field is optional; only those sent change. The venue and the period are left
    out on purpose: together they are the slot Venue Staff were asked about, so moving
    either means withdrawing this arrangement and raising another.
    """

    purpose = fields.String(validate=not_blank)
    expected_occupancy = fields.Integer(validate=validate.Range(min=1))
    required_layout = fields.String(
        validate=validate.OneOf(LayoutType.values()), allow_none=True
    )
    justification = fields.String(validate=not_blank)
```

Match `RaiseBookingRequestSchema`'s own field definitions as you read them in Step 1 — if its occupancy or layout validators differ from the above, copy **its** versions, so the two paths accept exactly the same values.

- [ ] **Step 5: Add the history recorder**

In `backend/app/modules/events/services.py`, below `record_venue_arrangement_withdrawn`:

```python
def record_venue_arrangement_changed(
    event_id: int,
    *,
    actor_id: int,
    details: dict[str, Any],
    session: Session | None = None,
) -> EventHistoryEntry:
    """Add the history entry for a changed arrangement, without committing (SCRUM-93).

    The entry rides in the caller's transaction, so it is saved with the change it
    records or not at all (ADR-0018).
    """
    event_request = resolve_session(session).get(EventRequest, event_id)
    return record_event_history(
        event_request,
        EventHistoryKind.VENUE_ARRANGEMENT_CHANGED,
        actor_id=actor_id,
        details=details,
        session=session,
    )
```

- [ ] **Step 6: Add the service**

Append to the SCRUM-93 section of `backend/app/modules/venue/services.py`. The constants go above the function, the helper above its caller:

```python
CHANGE_NOT_PENDING_MESSAGE = "Only a pending arrangement can be changed; this one is {status}."

#: What a coordinator may change on a pending arrangement (AC6). Not the venue or the
#: period: those identify the slot Venue Staff were asked about.
CHANGEABLE_FIELDS = ("purpose", "expected_occupancy", "required_layout", "justification")


def _changes_to_apply(
    arrangement: VenueBookingRequest, data: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Which of ``CHANGEABLE_FIELDS`` ``data`` actually alters, and from what.

    Every changeable field is a string, an integer or ``None``, so the previous and new
    values go into the history entry's details as they are.
    """
    changes: dict[str, dict[str, Any]] = {}
    for field in CHANGEABLE_FIELDS:
        if field not in data:
            continue
        previous = getattr(arrangement, field)
        if previous != data[field]:
            changes[field] = {"previous": previous, "new": data[field]}
    return changes


def change_arrangement(
    reference: str,
    arrangement_id: int,
    payload: Mapping[str, Any] | None,
    *,
    coordinator_id: int,
    session: Session | None = None,
) -> BookingRequestAsShown:
    """Change a pending arrangement's purpose, occupancy, layout or justification (AC6).

    Only the fields sent change, and only while Venue Staff have yet to decide: changing
    a decided arrangement would quietly void their decision. Suitability is re-checked
    against the merged values, so a change that outgrows the venue needs a justification
    just as raising one does — checked before anything is written, so a refused change
    leaves the arrangement exactly as it was. A change that alters nothing writes no
    history entry.

    Raises:
        ValidationError: 400 — invalid values, or no justification for a venue the
            changed arrangement no longer suits.
        NotFoundError: 404 — no such event among the coordinator's own, or no such
            arrangement on it.
        ConflictError: 409 — the arrangement is no longer pending.
    """
    from app.modules.events import services as event_services  # circular at import time

    schema = ChangeArrangementSchema()
    data = load_or_raise(schema, payload, partial=tuple(schema.fields))
    sess = resolve_session(session)
    event = event_services.get_event_for_coordinator(reference, coordinator_id, session=session)
    arrangement = _arrangement_of_event(event.id, arrangement_id, sess)
    if arrangement.status is not BookingRequestStatus.PENDING:
        raise ConflictError(CHANGE_NOT_PENDING_MESSAGE.format(status=arrangement.status.value))

    occupancy = data.get("expected_occupancy", arrangement.expected_occupancy)
    layout = data.get("required_layout", arrangement.required_layout)
    justification = data.get("justification", arrangement.justification)
    if not _venue_is_suitable(arrangement.venue_id, occupancy, layout, session) and not justification:
        raise ValidationError(
            "Invalid request.", details={"justification": [JUSTIFICATION_REQUIRED_MESSAGE]}
        )

    changes = _changes_to_apply(arrangement, data)
    if not changes:
        return show_booking_request(arrangement, event)

    for field, change in changes.items():
        setattr(arrangement, field, change["new"])
    event_services.record_venue_arrangement_changed(
        event.id,
        actor_id=coordinator_id,
        details={
            "venue_booking_request_id": arrangement.id,
            "venue_id": arrangement.venue_id,
            "changes": changes,
        },
        session=session,
    )
    sess.commit()
    return show_booking_request(arrangement, event)
```

Add `ChangeArrangementSchema` to the existing `from app.modules.venue.schemas import (...)` block, in alphabetical position.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `$PY -m pytest tests/venue/test_venue_arrangement_changes.py -q`
Expected: PASS, 10 tests. If the "leaves the stored row untouched" test fails, the suitability check is running after the values were applied — move it back above `_changes_to_apply`.

- [ ] **Step 8: Add the route**

In `backend/app/modules/venue/routes.py`, after the cancel-all route:

```python
@bp.patch("/events/<reference>/booking-requests/<int:arrangement_id>")
@requires_role(Role.EVENT_COORDINATOR)
def change_arrangement(reference: str, arrangement_id: int) -> tuple[Response, int]:
    """Change one of the coordinator's event's pending venue arrangements."""
    shown = services.change_arrangement(
        reference,
        arrangement_id,
        request.get_json(silent=True),
        coordinator_id=int(g.current_user_id),
    )
    return jsonify(_booking_request_schema.dump(shown)), 200
```

- [ ] **Step 9: Add the permission test**

Add a `venue.change_arrangement` case to `backend/tests/venue/test_venue_permissions.py`, in the file's existing style.

- [ ] **Step 10: Run lint and the whole suite**

```bash
$PY -m ruff format . && $PY -m ruff check . && $PY -m pytest -q
```

- [ ] **Step 11: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat(SCRUM-93): change a pending venue arrangement"
```

---

### Task 5: Close the already-met criteria, the ADR and the route table

**Files:**
- Modify: `backend/tests/venue/test_booking_requests.py` (append)
- Create: `docs/adr/0039-venue-arrangements.md`
- Modify: `README.md` (the route table, beside the two SCRUM-42 booking-request rows)
- Modify: `docs/adr/README.md` if it indexes ADRs — check first

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: no code.

- [ ] **Step 1: Confirm the already-met criteria are covered**

The spec claims SCRUM-42 already delivers AC1-AC5. Each has a test that would go red if the
behaviour broke; confirm all five are present and passing, and **report** rather than rewrite
if one is missing:

| AC | Test in `tests/venue/test_booking_requests.py` |
|---|---|
| AC1 several venues, overlapping times | `test_the_same_event_at_a_different_venue_and_overlapping_time_is_saved` |
| AC2 occupancy and layout default to the event's | `test_occupancy_and_layout_default_to_the_events`, `test_occupancy_and_layout_sent_override_the_events` |
| AC3 suitability per arrangement | `test_suitability_uses_the_requests_occupancy_not_the_events` |
| AC4 different venues never conflict | `test_the_same_event_at_a_different_venue_and_overlapping_time_is_saved` (same test as AC1) |
| AC5 the event's arrangements are listed | the `list_booking_requests_for_event` tests at the end of the file |

```bash
$PY -m pytest tests/venue/test_booking_requests.py -q
```

Expected: PASS. Write no new code and move no existing tests in this step — it exists so the
traceability table in the final report cites real test names rather than assumptions.

- [ ] **Step 2: Write the failing test for re-raising after a withdrawal**

Append to `backend/tests/venue/test_booking_requests.py` (it already imports what this needs; add `services.withdraw_arrangement`'s name only if the file does not already reach `services`):

```python
def test_the_same_venue_and_period_can_be_requested_again_after_a_withdrawal(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The pending index covers pending rows only, so withdrawing frees the slot
    (SCRUM-93, ADR-0035 §2)."""
    event = saved_event()
    first = raise_booking(venue, event, db_session)
    services.withdraw_arrangement(
        event.reference, first.id, coordinator_id=COORDINATOR_ID, session=db_session
    )

    second = raise_booking(venue, event, db_session)

    assert second.id != first.id
    assert len(saved_requests(db_session)) == 2
```

- [ ] **Step 3: Run it**

Run: `$PY -m pytest tests/venue/test_booking_requests.py -q`
Expected: PASS. This one passes immediately — it pins behaviour that falls out of the partial index rather than new code, which is why it is here and not in Task 1. If it **fails** with an `IntegrityError`, the partial index is not behaving as ADR-0035 §2 describes: stop and report it, do not change the index.

- [ ] **Step 4: Write ADR-0039**

Create `docs/adr/0039-venue-arrangements.md`. Read `docs/adr/0035-venue-booking-requests.md` first and follow its shape exactly: `# ADR-0039: <title>`, then **Status**, **Date** (2026-10-13), **Story**, `## Context`, `## Decision` as a numbered list, `## Consequences`, `## Revisit when`.

The decisions to record, each already argued in the spec — read
`docs/superpowers/specs/2026-10-13-scrum-93-venue-arrangements-design.md` and carry its reasoning across, with these as the numbered items:

1. An arrangement **is** a `VenueBookingRequest`; no new table and no rename, because SCRUM-42, 45 and 95 all build on it.
2. Only `withdrawn` is added to the status enum. `cancelled` waits for SCRUM-43, where `approved` first exists; adding it now would be a value no code can produce and no test can reach.
3. `RETIRED_REQUEST_STATUSES` defines "active" by exclusion, so `on_hold` counts as active when SCRUM-43/75 add it — which is what SCRUM-75's "more than one active venue arrangement" needs. Name SCRUM-75, SCRUM-49 and SCRUM-97 as the consumers.
4. Withdraw is `pending → withdrawn` only; any other status is a 409.
5. Arrangements keep a status instead of being deleted, unlike equipment lines, because SCRUM-75 and SCRUM-94 must be able to ignore retired ones — which requires them to exist.
6. `cancel-all` keeps AC6's own word although it only withdraws today, so SCRUM-43 widens it without renaming a published route.
7. Neither the venue nor the period changes on an existing arrangement; withdraw and raise another. Withdrawing frees the pending unique index, which is what makes this workable.
8. History entries (`venue_arrangement_changed`, `venue_arrangement_withdrawn`) are an audit trail the team asked for, not an AC — the same reasoning as ADR-0035 §8.
9. **Deferred acceptance criteria, each with its owner:** AC6's "cancelling" → SCRUM-43; AC4's conflict detection → SCRUM-44; `on_hold` in AC5 and AC7 → SCRUM-43 and SCRUM-75; releasing a confirmed `Booking` on cancellation → SCRUM-43; notifications → SCRUM-50.
10. **Defaults to review (not agreed with the team):** the five judgement calls under "Judgement calls to review at the end" in the spec. Copy them across verbatim so the team can overturn any of them.

- [ ] **Step 5: Add the routes to the README table**

In `README.md`, beside the two existing `booking-requests` rows, add three in the same format:

```
| `PATCH /api/venues/events/<reference>/booking-requests/<id>` | `event_coordinator` — change a pending arrangement's purpose, occupancy, layout or justification; the venue and period don't move |
| `POST  /api/venues/events/<reference>/booking-requests/<id>/withdraw` | `event_coordinator` — retract one arrangement before Venue Staff decide it; 409 if it isn't pending |
| `POST  /api/venues/events/<reference>/booking-requests/cancel-all` | `event_coordinator` — retire every arrangement the event still has |
```

- [ ] **Step 6: Run the full definition-of-done checks**

```bash
$PY -m ruff format . && $PY -m ruff check .
$PY -m pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=xml -q
$PY -m diff-cover coverage.xml --compare-branch=origin/feat/SCRUM-95-lead-assignment-queue --fail-under=100
```

Expected: lint clean; every test passing; `diff-cover` at 100%. Also read the `Missing` column for `venue/services.py`, `venue/schemas.py`, `events/services.py`, `venue/models.py` and `events/models.py`: `diff-cover` cannot see branches, so any `a->b` entry on a line this branch added is a gap you must either test or justify with `# pragma: no cover - <reason>`.

- [ ] **Step 7: Commit**

```bash
git add backend/tests docs README.md
git commit -m "docs(SCRUM-93): record the arrangement decisions as ADR-0039"
```

---

## After the last task

Run the `review-checklist` skill over the whole branch (`git diff feat/SCRUM-95-lead-assignment-queue...HEAD`), fix every **must** and **should** it finds, re-run the Task 5 Step 6 checks, and report:

- the acceptance-criteria traceability table, with each deferred AC pointing at its owning story;
- every check, passed or failed;
- every coverage gap with its reason;
- what the self-review found and fixed, and anything left open with why;
- the five judgement calls from the spec, for the team to confirm or overturn.
