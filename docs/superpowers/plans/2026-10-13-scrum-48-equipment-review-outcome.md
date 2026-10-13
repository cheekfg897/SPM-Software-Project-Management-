# SCRUM-48 Equipment Review Outcome Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Technical Support Staff record — and later revise — the outcome of their review against an event's equipment request, so the coordinator sees what will actually be provided without chasing them.

**Architecture:** The outcome lives on the existing `EventEquipmentLine` (one line = one request for a type). Four new nullable columns hold it, and `provided_quantity IS NULL` is the single meaning of "no outcome yet" — the predicate SCRUM-97 and SCRUM-49 gate on. The status is *derived* by the one service that writes the outcome, never supplied by the caller, so the status and the quantity cannot drift apart.

**Tech Stack:** Python 3.13, Flask, SQLAlchemy 2 (`Mapped`/`mapped_column`), marshmallow, Alembic, pytest. Unit suite only: no Postgres, no Flask test client.

**Spec:** this document. The "Design decisions" section below is the spec; the tasks argue from it. There is no separate spec file — the ACs are concrete and the decisions are recorded here and, at the end, in ADR-0040.

**Jira:** [SCRUM-48](https://smu-team-uu78imq6.atlassian.net/browse/SCRUM-48), last edited 2026-10-04 — untouched by the 2026-10-13 requirements sweep, so its ACs are stable.

**Branch:** `feat/SCRUM-48-equipment-review-outcome`, branched from `feat/SCRUM-93-venue-arrangements` so migration `0024` can chain on SCRUM-93's `0023`. SCRUM-93 is still in flight; when it finishes, this branch rebases onto its final tip. Expect mechanical conflicts in the append regions of `events/models.py` (enum members) and `events/services.py`.

## What changed during implementation

This plan is the historical design; three names in it differ from what shipped. Read the code
and ADR-0040 as authoritative:

- `has_recorded_outcomes` was renamed **`all_outcomes_recorded`**, which is what SCRUM-97 and
  SCRUM-49 should build on.
- `OUTCOME_STATUSES` was deleted as unused.
- Migration `0024`'s revision id is **`0024_add_equipment_outcome`**, not
  `0024_add_equipment_review_outcome` — the latter is 33 characters and `alembic_version` is
  `VARCHAR(32)`. Later migrations must chain on the shorter id.

ADR-0040 records the rest, including the follow-ups this plan did not anticipate.

## Global Constraints

- **British spelling** in code and API (`organiser`, `serialise`, `fulfilled`, `cancelled`).
- **Module boundaries.** A module never imports another module's `models`. `events/services.py` and `equipment/services.py` already import each other **as modules** (`from app.modules.equipment import services as equipment_services`) — keep that form. `app/common/` never imports from `app/modules/`.
- **Layers.** `routes.py` thin: parse → call service → serialise. Services raise `AppError` subclasses from `app.common.errors`; routes never build error responses. Every error body is `{"error", "message", "details?"}`.
- **Auth:** `@requires_auth` / `@requires_role(Role.X)` from `app.common.decorators`. Never spell a role string by hand — use `Role` from `app.modules.auth.permissions`.
- **Dates:** never `date.today()` or a naive `datetime.now()` (ruff DTZ blocks them). Business dates come from `app.common.clock.local_today()`; validation takes `today` as a parameter.
- **Service signatures** take keyword-only `session: Session | None = None`, resolved with `resolve_session(session)`.
- **Helpers first:** a helper sits ABOVE the functions that use it, in every file.
- **No repeated code**, in tests too. Extract on the second real use.
- **No decorative tests:** every test asserts an observable outcome and goes red if the code it covers breaks.
- **Every test module** sets `pytestmark = pytest.mark.scrum_48`; declare that marker in `pytest.ini` (`--strict-markers`).
- **Exactly ONE migration** on this branch: `0024`, chained on `0023_add_withdrawn_arrangements`.
- **Postgres IS available** at `/opt/homebrew/opt/postgresql@18` (`initdb`, `pg_ctl`, `psql`). The unit suite mocks the DB, but a migration must NOT be signed off by reading alone: stand up a throwaway cluster, replay `upgrade()` → `downgrade()` → `upgrade()` with representative rows present, then tear the cluster down. CI replays the same sequence. This instruction exists because on 2026-10-13 SCRUM-93's migration passed a careful read and then failed on a real cluster for two separate reasons:
  - **A predicate index breaks an enum rebuild.** `ALTER TYPE x RENAME TO x_old` plus `ALTER COLUMN … TYPE x USING …` makes Postgres re-create any index whose *predicate* mentions that column, deparsed against the renamed type — `operator does not exist: x = x_old`. Before rebuilding `event_equipment_line_status`, run `\d event_equipment_lines` on the cluster and check for any index or constraint whose definition mentions `status`; drop it before the rebuild and re-create it after.
  - **Re-pointing rows on downgrade can violate a unique constraint.** `event_equipment_lines` has `uq_event_equipment_lines_event_request_id_equipment_type_id` on (`event_request_id`, `equipment_type_id`). That one has no predicate, so reverting a status cannot collide on it — but verify that on the cluster rather than assuming, and prefer deleting rows whose enum value is disappearing (migration 0022's precedent) over re-pointing them.
- **Conventional Commit subjects** naming the story: `feat(SCRUM-48): ...`. **Never add a `Co-Authored-By` line or any AI/model attribution to a commit or PR** — the repo forbids it.
- Run from `backend/`:
  ```bash
  export PY=/Users/ernesttan/Desktop/SMU/Y3S1/SPM/SPM-Software-Project-Management-/backend/.venv/bin/python
  cd /Users/ernesttan/Desktop/SMU/Y3S1/SPM/spm-worktrees/SCRUM-48/backend
  ```
  `$PY -m ruff`, `$PY -m pytest` and `$PY -m diff-cover` all work. Read files with Bash (`cat`, `sed -n`) if the Read tool is blocked outside the main repo.

## Design decisions (the spec)

1. **The outcome belongs to the line, not to a reservation.** `EquipmentReservation` rows (SCRUM-46) record what was actually held, keyed by event and type with no link to a line. The outcome is Technical Support's *statement* about a request, which may differ from reservations (they can declare "unavailable" without reserving anything). So it is stored on `EventEquipmentLine`, not derived from reservations.

2. **`provided_quantity` is the source of truth; the status is derived.** The service computes the status from `provided_quantity` against the line's `quantity`:

   | Condition | Status |
   |---|---|
   | `provided == quantity` | `FULFILLED` (AC2) |
   | `0 < provided < quantity` | `PARTIALLY_FULFILLED` (AC1) |
   | `provided == 0` | `UNAVAILABLE` (AC3) |

   The caller never sends a status. One writer, so the two can never disagree. `provided_quantity > quantity` is a 400.

3. **The shortfall is derived, never stored:** `quantity - provided_quantity` (AC1). Do not add a column for it. Note this is a *different* quantity from `EquipmentAvailability.shortfall` (`equipment/services.py:53`), which is availability against a request — do not reuse that name on the line.

4. **`provided_quantity IS NULL` means "no outcome recorded yet".** This is the seam SCRUM-97 and SCRUM-49 gate on: today's requirements sweep made "every equipment request has a recorded outcome" a precondition for Safety Review, and deleted the old "acknowledge and proceed" escape. Task 1 exposes it as a named function so those stories do not re-derive it.

5. **A note is required whenever `provided < quantity`** — AC3 says a reason is required when nothing is available, and AC1 shows a note beside a partial outcome. A fulfilled outcome needs none. *(Judgement call: AC1 does not say the note is mandatory for a partial outcome. Recorded in ADR-0040 for the team to overturn.)*

6. **The coordinator is notified on every recorded outcome**, not only on `UNAVAILABLE`. AC3 names the notification explicitly, but SCRUM-97's own team assumption says *"Any outcome recorded by Technical Support, including partially fulfilled or unavailable, counts as their decision; the coordinator is notified of it (SCRUM-48)"*. *(Judgement call, recorded in ADR-0040.)*

7. **An outcome can be revised with no guard (AC5).** Recording again overwrites the columns and writes another history entry, so the trail shows the revision. There is no "already recorded" conflict.

8. **AC6 is deferred.** *"Given the event has already passed its Operational Safety Check, When the outcome is revised, Then the event must pass a new safety check"* — Safety Review does not exist yet; **SCRUM-97 and SCRUM-98** own it. ADR-0040 names them, following ADR-0035 §13's pattern of listing each deferred criterion against its owner.

9. **Recording an outcome takes the line off Technical Support's queue.** `list_equipment_requests_awaiting_action` (`events/services.py:1469`) filters on `EquipmentLineStatus.REQUESTED`, so a line with an outcome drops out automatically. That is correct and gets a test — it is the one existing behaviour this change alters.

## Review Focus

Input classes the ACs imply but no happy path exercises. Each has its test in the owning task.

1. **`provided_quantity` greater than the line's `quantity`** — must be a 400, not a negative shortfall. (Task 2)
2. **A partial or unavailable outcome with a blank or whitespace-only note** — must be refused; `not_blank` on the field is not enough, because the field is optional for a fulfilled outcome. (Task 2)
3. **An Event Coordinator calling the outcome route** — must be 403; only Technical Support records an outcome. (Task 2)
4. **A line id belonging to a different event** — must be 404, not a cross-event write. (Task 2)
5. **Revising an outcome from `UNAVAILABLE` back to `FULFILLED`** — must clear the shortfall and leave exactly two history entries, so AC5's revision is visible rather than overwritten silently. (Task 2)

---

### Task 1: Outcome storage, the derived statuses, migration 0024, and the no-outcome seam

**Files:**
- Modify: `backend/app/modules/events/models.py` — `EquipmentLineStatus` (at :131), `EventEquipmentLine` (at :281), `EventHistoryKind` (at :68)
- Modify: `backend/app/modules/notifications/models.py` — `NotificationKind` (at :24)
- Modify: `backend/app/modules/events/services.py` — append a SCRUM-48 section
- Create: `backend/migrations/versions/0024_add_equipment_review_outcome.py`
- Modify: `backend/pytest.ini`
- Test: `backend/tests/events/test_equipment_outcome.py`

**Interfaces:**
- Consumes: `EventEquipmentLine`, `EquipmentLineStatus`, `UTCDateTime` from `app.common.database`, `resolve_session`.
- Produces: `EquipmentLineStatus.FULFILLED` / `.PARTIALLY_FULFILLED` / `.UNAVAILABLE`; the columns `provided_quantity`, `outcome_note`, `reviewed_by`, `reviewed_at`; `OUTCOME_STATUSES: frozenset[EquipmentLineStatus]`; `outcome_status_for(quantity: int, provided: int) -> EquipmentLineStatus`; `lines_without_outcome(event_id: int, *, session: Session | None = None) -> list[EventEquipmentLine]`; `has_recorded_outcomes(event_id: int, *, session: Session | None = None) -> bool`; `EventHistoryKind.EQUIPMENT_OUTCOME_RECORDED`; `NotificationKind.EQUIPMENT_OUTCOME_RECORDED`.

- [ ] **Step 1: Declare the marker**

Add to `backend/pytest.ini`'s `markers` block, after the `scrum_95` line:

```
    scrum_48: tests for SCRUM-48 "record the outcome of an equipment review"
```

- [ ] **Step 2: Read the three patterns you will copy**

Read these before writing anything — your code mirrors them:
- `backend/app/modules/events/models.py:281-320` — `EventEquipmentLine` as it stands, including how `status` declares its enum with `values_callable`.
- `backend/migrations/versions/0023_add_withdrawn_arrangements.py` — the enum-addition and downgrade pattern (adds values in an `autocommit_block()`, rebuilds each type on downgrade). Your migration does the same **plus** `op.add_column` / `op.drop_column` for four columns.
- `backend/app/modules/equipment/models.py:86-127` — `EquipmentReservation`, for how a nullable `UTCDateTime` and a `users.id` foreign key are declared in this codebase.

- [ ] **Step 3: Write the failing test**

Create `backend/tests/events/test_equipment_outcome.py`. This task's tests cover only the derivation and the seam; recording is Task 2.

```python
"""Unit tests for SCRUM-48 — the outcome of an equipment review.

This file covers how an outcome's status follows from the quantity provided, and the
"no outcome yet" seam that SCRUM-97 and SCRUM-49 gate the Safety Review on.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.modules.events import services
from app.modules.events.models import EquipmentLineStatus, EventEquipmentLine, EventRequest
from app.modules.equipment.models import EquipmentType

pytestmark = pytest.mark.scrum_48


@pytest.mark.parametrize(
    ("quantity", "provided", "expected"),
    [
        (10, 10, EquipmentLineStatus.FULFILLED),
        (10, 6, EquipmentLineStatus.PARTIALLY_FULFILLED),
        (10, 0, EquipmentLineStatus.UNAVAILABLE),
        (1, 1, EquipmentLineStatus.FULFILLED),
    ],
    ids=["all", "some", "none", "single-unit"],
)
def test_the_status_follows_from_how_much_was_provided(
    quantity: int, provided: int, expected: EquipmentLineStatus
) -> None:
    assert services.outcome_status_for(quantity, provided) is expected


def test_a_new_line_has_no_recorded_outcome(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> None:
    line = make_equipment_line(saved_event_request, equipment_type, quantity=10)
    save(line)

    assert line.provided_quantity is None
    assert services.lines_without_outcome(saved_event_request.id, session=db_session) == [line]
    assert services.has_recorded_outcomes(saved_event_request.id, session=db_session) is False


def test_a_line_with_an_outcome_drops_out_of_the_no_outcome_list(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> None:
    """SCRUM-97 gates Safety Review on this list being empty."""
    line = make_equipment_line(saved_event_request, equipment_type, quantity=10)
    save(line)
    line.provided_quantity = 10
    line.status = EquipmentLineStatus.FULFILLED
    db_session.commit()

    assert services.lines_without_outcome(saved_event_request.id, session=db_session) == []
    assert services.has_recorded_outcomes(saved_event_request.id, session=db_session) is True


def test_an_event_with_no_equipment_has_no_lines_awaiting_an_outcome(
    db_session: Session, saved_event_request: EventRequest
) -> None:
    assert services.lines_without_outcome(saved_event_request.id, session=db_session) == []
    assert services.has_recorded_outcomes(saved_event_request.id, session=db_session) is False
```

Check `make_equipment_line`'s signature in `backend/tests/conftest.py:407` before using it — it is `(event_request, equipment_type, *, quantity=2, notes="Needs HDMI", ...)`. If it does not accept `quantity` as shown, use whatever it does accept and say so in your report.

- [ ] **Step 4: Run the test to verify it fails**

Run: `$PY -m pytest tests/events/test_equipment_outcome.py -q`
Expected: FAIL — `AttributeError` on `services.outcome_status_for`, and `FULFILLED` missing from `EquipmentLineStatus`.

- [ ] **Step 5: Add the statuses and the columns**

In `backend/app/modules/events/models.py`, replace `EquipmentLineStatus` (at :131) with:

```python
class EquipmentLineStatus(str, enum.Enum):
    """Where an event's equipment line stands (SCRUM-37 AC4, ADR-0019, SCRUM-48).

    ``REQUESTED`` until Technical Support records the outcome of their review, which
    is then one of the three outcome values. The outcome follows from how much was
    provided: :func:`app.modules.events.services.outcome_status_for` is the only
    place that decides, so the status and ``provided_quantity`` cannot disagree.
    """

    REQUESTED = "requested"
    #: Everything the coordinator asked for will be provided (SCRUM-48 AC2).
    FULFILLED = "fulfilled"
    #: Some but not all of it; the shortfall is ``quantity - provided_quantity``
    #: and a note says why (SCRUM-48 AC1).
    PARTIALLY_FULFILLED = "partially_fulfilled"
    #: None of it is available; the note carries the required reason (SCRUM-48 AC3).
    UNAVAILABLE = "unavailable"
```

Then add four columns to `EventEquipmentLine`, directly after its `status` column (around :318):

```python
    #: How many units Technical Support will actually provide (SCRUM-48). ``None``
    #: means no outcome has been recorded yet, which is what SCRUM-97 and SCRUM-49
    #: gate the Safety Review on; the shortfall is ``quantity`` minus this.
    provided_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Why the request could not be met in full. Required when less than the whole
    #: quantity is provided (SCRUM-48 AC1, AC3).
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The Technical Support user who recorded the outcome, shown by name on the
    #: event record (SCRUM-48 AC4).
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
```

Add a check constraint to `EventEquipmentLine.__table_args__`, beside the existing `ck_event_equipment_lines_quantity_min`:

```python
        CheckConstraint(
            "provided_quantity IS NULL OR provided_quantity BETWEEN 0 AND quantity",
            name="ck_event_equipment_lines_provided_within_quantity",
        ),
```

Add whatever imports these need (`Text`, `ForeignKey`, `CheckConstraint`, `UTCDateTime`, `datetime`) only if the file does not already have them — check first.

- [ ] **Step 6: Add the history and notification kinds**

In `backend/app/modules/events/models.py`, append to `EventHistoryKind` after its last member:

```python
    #: Technical Support recorded or revised the outcome of an equipment review;
    #: ``details`` holds ``equipment_line_id``, ``equipment_type_id``,
    #: ``equipment_type_name``, ``quantity``, ``provided_quantity``, ``status`` and
    #: ``note`` (``None`` when the request was met in full), and ``actor_id`` is the
    #: reviewer (SCRUM-48 AC4, AC5).
    EQUIPMENT_OUTCOME_RECORDED = "equipment_outcome_recorded"
```

In `backend/app/modules/notifications/models.py`, append to `NotificationKind`:

```python
    #: Technical Support recorded the outcome of an equipment review, so the
    #: coordinator knows what will be provided (SCRUM-48 AC3).
    EQUIPMENT_OUTCOME_RECORDED = "equipment_outcome_recorded"
```

Check whether `equipment_reserved` history entries are hidden from organisers in `_shown_to_organiser` (`events/services.py:1769`). An equipment outcome is internal in the same way, so add the new kind wherever `EQUIPMENT_RESERVED` is excluded. Say in your report what you found and what you did.

- [ ] **Step 7: Add the derivation and the seam**

Append a new section to the **end** of `backend/app/modules/events/services.py`:

```python
# --------------------------------------------------------------------------
# SCRUM-48 — record the outcome of an equipment review
# --------------------------------------------------------------------------

#: The statuses that mean an outcome has been recorded (SCRUM-48).
OUTCOME_STATUSES = frozenset(
    {
        EquipmentLineStatus.FULFILLED,
        EquipmentLineStatus.PARTIALLY_FULFILLED,
        EquipmentLineStatus.UNAVAILABLE,
    }
)


def outcome_status_for(quantity: int, provided: int) -> EquipmentLineStatus:
    """Which outcome ``provided`` units against a request for ``quantity`` is.

    The only place the outcome status is decided, so it can never disagree with the
    quantity stored beside it (SCRUM-48 AC1-AC3).
    """
    if provided == quantity:
        return EquipmentLineStatus.FULFILLED
    if provided == 0:
        return EquipmentLineStatus.UNAVAILABLE
    return EquipmentLineStatus.PARTIALLY_FULFILLED


def lines_without_outcome(
    event_id: int, *, session: Session | None = None
) -> list[EventEquipmentLine]:
    """The event's equipment lines Technical Support has not yet ruled on (SCRUM-48).

    SCRUM-97 and SCRUM-49 refuse to let an event into Safety Review while this is
    not empty: every equipment request must carry a recorded outcome first.
    """
    query = (
        select(EventEquipmentLine)
        .where(
            EventEquipmentLine.event_request_id == event_id,
            EventEquipmentLine.provided_quantity.is_(None),
        )
        .order_by(EventEquipmentLine.id)
    )
    return list(resolve_session(session).scalars(query).all())


def has_recorded_outcomes(event_id: int, *, session: Session | None = None) -> bool:
    """Whether every one of the event's equipment lines has an outcome (SCRUM-48).

    ``True`` for an event with no equipment at all, because nothing is outstanding.
    """
    return not lines_without_outcome(event_id, session=session)
```

**Careful:** the test asserts `has_recorded_outcomes(...) is False` for an event whose only line has no outcome, and `is False` for an event with no equipment at all. Read the test in Step 3 again — for the *no equipment* case it expects `False`. That contradicts the docstring above. **Resolve it this way:** keep the function's meaning as "every line has an outcome", change the docstring to say an event with no equipment returns `True`, and change that one assertion in the Step 3 test from `is False` to `is True` for the no-equipment case, with a comment saying why. Report that you did so.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `$PY -m pytest tests/events/test_equipment_outcome.py -q`
Expected: PASS.

- [ ] **Step 9: Write migration 0024**

Create `backend/migrations/versions/0024_add_equipment_review_outcome.py`, mirroring `0023_add_withdrawn_arrangements.py`. It must:

- set `revision = "0024_add_equipment_review_outcome"` and `down_revision = "0023_add_withdrawn_arrangements"`;
- in `upgrade()`: `op.add_column` the four columns on `event_equipment_lines`, add the check constraint, and then **in a separate `autocommit_block()`** add the three `event_equipment_line_status` values, the `event_history_entry_kind` value and the `notification_kind` value;
- in `downgrade()`: delete the new history and notification rows, re-point any line whose status is one of the three new values back to `'requested'` and null its four columns, drop the constraint and the columns, then rebuild all three enum types without the added values. **Check for predicate indexes on `status` first** (see Global Constraints) and drop/re-create any you find around the rebuild.

Then **replay it on a real cluster** — `upgrade()`, insert a line in each of the three new statuses, `downgrade()`, `upgrade()` — and paste the commands and output into your report. A migration verified only by reading is not verified.

The `PREVIOUS_*_VALUES` tuples must list exactly what exists on this branch *before* this migration. Derive each by reading the enum in the model file and subtracting what this migration adds — and cross-check `event_history_entry_kind` against `0023`'s `PREVIOUS_HISTORY_KIND_VALUES` plus the two values 0023 itself adds. A wrong list silently corrupts the downgrade, and CI replays downgrade → upgrade.

Verify exactly one migration chains on 0023:

```bash
grep -rn "down_revision" migrations/versions/ | grep 0023_add_withdrawn_arrangements
```

Expected: exactly one line.

- [ ] **Step 10: Lint and the full suite**

```bash
$PY -m ruff format . && $PY -m ruff check . && $PY -m pytest -q
```

Expected: formatted, `All checks passed!`, everything passing. Adding enum values will break any existing test that asserts the *equality* of a migration's enum list with a model enum — the pattern is that such tests use `<=` for shared enums. If one fails, read its neighbours in the same file and follow that file's own convention, then report exactly what you changed and why.

- [ ] **Step 11: Commit**

```bash
git add backend/pytest.ini backend/app backend/migrations backend/tests
git commit -m "feat(SCRUM-48): record how much of an equipment request can be met"
```

---

### Task 2: Record and revise an outcome

**Files:**
- Modify: `backend/app/modules/events/schemas.py` — a new payload schema
- Modify: `backend/app/modules/events/services.py` — the SCRUM-48 section
- Modify: `backend/app/modules/events/routes.py` — after `remove_equipment` (at :294)
- Test: `backend/tests/events/test_equipment_outcome.py` (append); `backend/tests/events/test_equipment_outcome_permissions.py` (create)

**Interfaces:**
- Consumes: everything Task 1 produced; `record_event_history`; `_raise_notifications` or `notify_users`; the `EventSummary` dataclass.
- Produces: `RecordEquipmentOutcomeSchema`; `record_equipment_outcome(reviewer_id, reference, line_id, payload, *, session=None) -> EventEquipmentLine`; the messages `OUTCOME_NOTE_REQUIRED_MESSAGE`, `PROVIDED_ABOVE_REQUESTED_MESSAGE`, `EQUIPMENT_LINE_NOT_FOUND_MESSAGE`.

- [ ] **Step 1: Read the two patterns you will copy**

- `backend/app/modules/equipment/services.py:380` — `reserve_equipment`: how a sibling action validates, writes, records history in the same commit, commits, then notifies in a second commit.
- `backend/app/modules/events/services.py:2173` — `record_equipment_reserved`, and `:2206` — `notify_coordinator_equipment_reserved`. Your notification follows the second exactly, including its `_warn_unassigned` path when the event has no coordinator.

Note which guard controls reading a line: `_event_request_for_equipment_viewer` (`:1124`) lets Technical Support reach any event's lines, while a coordinator may reach only their own. Technical Support records the outcome, so **use the Technical-Support-capable lookup, not `_event_request_assigned_to`.**

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/events/test_equipment_outcome.py` tests for each of these, named for what they assert. Use the existing fixtures (`db_session`, `save`, `saved_event_request`, `equipment_type`, `make_equipment_line`, `notifications_of`, and `history_of` from `tests/events/conftest.py:193`):

1. a fulfilled outcome sets `provided_quantity`, status `FULFILLED`, `reviewed_by` and `reviewed_at`, and needs no note;
2. ten requested with six provided gives `PARTIALLY_FULFILLED` and a shortfall of four *(assert the shortfall as `line.quantity - line.provided_quantity`; there is no stored column)*;
3. zero provided gives `UNAVAILABLE` and keeps the note;
4. **Review Focus 2** — a partial or unavailable outcome with a whitespace-only note is a `ValidationError` on `note`, and the line is unchanged;
5. a fulfilled outcome with no note is accepted;
6. **Review Focus 1** — `provided_quantity` above the line's `quantity` is a `ValidationError`, and the line is unchanged;
7. the coordinator is notified, with the kind `EQUIPMENT_OUTCOME_RECORDED` (AC3, AC6 of the design);
8. an event with no coordinator logs a warning and still records the outcome (copy how `notify_coordinator_equipment_reserved`'s test covers `_warn_unassigned`);
9. one history entry is written, carrying `equipment_line_id`, `quantity`, `provided_quantity`, `status` and `note` (AC4);
10. **Review Focus 5** — revising `UNAVAILABLE` → `FULFILLED` clears the note, sets the full quantity, and leaves exactly **two** history entries (AC5);
11. **Review Focus 4** — a line id belonging to another event is a `NotFoundError`;
12. recording an outcome takes the line off `list_equipment_requests_awaiting_action` (design decision 9).

Then create `backend/tests/events/test_equipment_outcome_permissions.py` with `pytestmark = pytest.mark.scrum_48`, copying the parametrised pattern in `backend/tests/events/test_lead_assignment_permissions.py`: the route allows **only** `Role.TECHNICAL_SUPPORT_STAFF` (**Review Focus 3**), every other role gets 403 without the service being called, and no token gives 401.

- [ ] **Step 3: Run them to verify they fail**

Run: `$PY -m pytest tests/events/test_equipment_outcome.py tests/events/test_equipment_outcome_permissions.py -q`
Expected: FAIL — no `record_equipment_outcome`, no route.

- [ ] **Step 4: Add the payload schema**

In `backend/app/modules/events/schemas.py`, beside the other equipment schemas:

```python
class RecordEquipmentOutcomeSchema(Schema):
    """Payload for recording the outcome of an equipment review (SCRUM-48).

    ``provided_quantity`` is how many units will actually be provided; the status and
    the shortfall follow from it. ``note`` is required unless the whole request is
    met, and it is where AC3's reason goes.
    """

    provided_quantity = fields.Integer(required=True, validate=validate.Range(min=0))
    note = fields.String(validate=not_blank, allow_none=True, load_default=None)
```

Match the file's own idiom for `not_blank` and `validate.Range` as you find them — if `not_blank` is spelled differently there, use the file's version.

- [ ] **Step 5: Write the service**

Append to the SCRUM-48 section of `backend/app/modules/events/services.py`. Constants above the function, helper above its caller. The order of checks matters and is tested:

1. load the payload (400 on an invalid shape);
2. find the event and its line, Technical-Support-capable (404 for an unknown reference or a line on another event);
3. refuse `provided_quantity > line.quantity` with `PROVIDED_ABOVE_REQUESTED_MESSAGE` on `provided_quantity`;
4. refuse a missing or blank note when `provided_quantity < line.quantity`, with `OUTCOME_NOTE_REQUIRED_MESSAGE` on `note`;
5. set `provided_quantity`, `outcome_note` (`None` when the request is met in full — do not keep a stale note from a previous outcome), `status` via `outcome_status_for`, `reviewed_by` and `reviewed_at`;
6. write the history entry in the same transaction, then commit once;
7. notify the coordinator in a second commit, logging and swallowing a failure exactly as `notify_coordinator_equipment_reserved` does.

`reviewed_at` must come from the application clock, not `datetime.now()` — follow how another service in this file stamps a time, and take `now` as a parameter if that is the local convention so tests can pin it.

- [ ] **Step 6: Run the service tests**

Run: `$PY -m pytest tests/events/test_equipment_outcome.py -q`
Expected: PASS.

- [ ] **Step 7: Add the route**

In `backend/app/modules/events/routes.py`, after `remove_equipment` (at :294). The existing equipment paths are `/requests/<reference>/equipment` and `/requests/<reference>/equipment/<int:line_id>`, so:

```python
@bp.post("/requests/<reference>/equipment/<int:line_id>/outcome")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def record_equipment_outcome(reference: str, line_id: int) -> tuple[Response, int]:
    """Record or revise the outcome of this event's equipment review."""
```

Serialise with whatever schema the other equipment-line routes use for a line, extended in Task 3. Return 200.

- [ ] **Step 8: Run the permission tests, then lint and the full suite**

```bash
$PY -m pytest tests/events/test_equipment_outcome_permissions.py -q
$PY -m ruff format . && $PY -m ruff check . && $PY -m pytest -q
```

- [ ] **Step 9: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat(SCRUM-48): let Technical Support record and revise a review outcome"
```

---

### Task 3: Show the outcome on the event record

**Files:**
- Modify: `backend/app/modules/events/schemas.py` — the equipment-line output schema
- Modify: `backend/app/modules/events/services.py` — whatever dataclass carries a line to the API
- Test: `backend/tests/events/test_equipment_outcome.py` (append)

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: the outcome fields on the serialised line — `status`, `provided_quantity`, `shortfall`, `outcome_note`, `reviewed_by` (the reviewer's **full name**, not an id), `reviewed_at`.

- [ ] **Step 1: Find how a line reaches the API today**

```bash
grep -n "EventEquipmentLine\|equipment_line" app/modules/events/schemas.py | head -20
grep -n "shown_line\|line_as_shown" tests/events/conftest.py
```

Read the schema and any `*AsShown` dataclass in the chain. AC4 needs the **reviewing staff member** shown by name; the precedent is `ReservationAsShown.reserved_by: str | None` (`equipment/services.py:56`), which resolves a user id to a full name. Follow it, and leave the raw `reviewed_by` id out of the response — no other response in this codebase exposes a user id.

- [ ] **Step 2: Write the failing tests**

Append tests asserting that a serialised line carries: the outcome status, `provided_quantity`, a derived `shortfall`, the note, the reviewer's full name, and `reviewed_at`; that all of them are `None`/absent for a line with no outcome yet; and that a reviewer whose user row no longer exists serialises as `None` rather than raising (follow how `ReservationAsShown` handles that — check whether it does, and if it does not, say so in your report rather than inventing behaviour).

- [ ] **Step 3: Run, implement, re-run**

Run them to see them fail, implement the smallest change to the schema and the shown dataclass, run again to see them pass.

- [ ] **Step 4: Lint and the full suite, then commit**

```bash
$PY -m ruff format . && $PY -m ruff check . && $PY -m pytest -q
git add backend/app backend/tests
git commit -m "feat(SCRUM-48): show the review outcome and its reviewer on the event record"
```

---

### Task 4: ADR-0040, the route table, and the coverage gate

**Files:**
- Create: `docs/adr/0040-equipment-review-outcome.md`
- Modify: `README.md` (route table)

- [ ] **Step 1: Write ADR-0040**

Read `docs/adr/0035-venue-booking-requests.md` first and follow its shape exactly: `# ADR-0040: <title>`, then **Status** (Accepted), **Date** (2026-10-13), **Story**, `## Context`, `## Decision` as a numbered list, `## Consequences`, `## Revisit when`.

Carry across the nine decisions in this plan's "Design decisions" section, with their reasoning. Then add, as the last two numbered items:

- **Deferred acceptance criteria, each with its owner:** AC6 (a revised outcome forces a new Operational Safety Check) → **SCRUM-97** and **SCRUM-98**; notifications beyond the coordinator → **SCRUM-50**.
- **Defaults to review (not agreed with the team):** design decisions 5 (a note is required for a partial outcome, not only for an unavailable one) and 6 (the coordinator is notified of every outcome, not only an unavailable one), plus anything the implementers flagged in their reports.

- [ ] **Step 2: Add the route to the README table**

Add one row beside the existing `/requests/<reference>/equipment` rows:

```
| `POST /api/events/requests/<reference>/equipment/<line_id>/outcome` | `technical_support_staff` — record or revise the review outcome; a note is required unless the whole request is met; the coordinator is notified |
```

Check the table's exact column format first and match it.

- [ ] **Step 3: Run the full definition-of-done checks**

```bash
$PY -m ruff format . && $PY -m ruff check .
$PY -m pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=xml -q
$PY -m diff-cover coverage.xml --compare-branch=origin/feat/SCRUM-93-venue-arrangements --fail-under=100
```

Expected: lint clean, every test passing, `diff-cover` 100%. Then read the `Missing` column for `events/services.py`, `events/models.py`, `events/schemas.py`, `events/routes.py` and `notifications/models.py`: `diff-cover` cannot see branches, so any `a->b` on a line this branch added is a gap to test or to justify with `# pragma: no cover - <reason>`.

- [ ] **Step 4: Commit**

```bash
git add docs README.md
git commit -m "docs(SCRUM-48): record the equipment outcome decisions as ADR-0040"
```

---

## After the last task

Run the `review-checklist` skill over the whole branch (`git diff feat/SCRUM-93-venue-arrangements...HEAD`), fix every **must** and **should**, re-run Task 4 Step 3, and report:

- the AC traceability table, with AC6 pointing at SCRUM-97/98;
- every check, passed or failed;
- every coverage gap with its reason;
- what the self-review found and fixed, and anything left open with why;
- the judgement calls (design decisions 5 and 6 at minimum) for the team to confirm or overturn.
