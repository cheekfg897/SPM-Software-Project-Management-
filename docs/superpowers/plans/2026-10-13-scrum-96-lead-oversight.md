# SCRUM-96 Lead Oversight and Reassignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move reassignment from any coordinator to the Event Coordinator Lead, give the Lead the two oversight views they need to balance workload, notify the coordinator who loses an event, and close the one read path by which a coordinator can still see an event that is not theirs.

**Architecture:** Almost nothing new is built. SCRUM-87 already reassigns an event, writes the history entry and removes the previous coordinator's access as a side effect of `coordinator_id` being the only link; SCRUM-95 already added the Lead role. This story changes who may call reassignment, adds two list endpoints, adds one notification recipient, and scopes `list_event_history`. The only genuinely new concept is "active event", which AC1 needs and no code defines.

**Tech Stack:** Python 3.13, Flask, SQLAlchemy 2, marshmallow, Alembic, pytest. Unit suite only: no Postgres needed for the tests, no Flask test client.

**Spec:** this document — the "Design decisions" section is the spec and the tasks argue from it. The ACs are concrete; the decisions are recorded here and, at the end, in ADR-0041.

**Jira:** [SCRUM-96](https://smu-team-uu78imq6.atlassian.net/browse/SCRUM-96), last edited 2026-10-13 09:00 (that edit reworded AC6 from "manage" to "**view and** manage").

**Branch:** `feat/SCRUM-96-lead-oversight`, branched from `feat/SCRUM-95-lead-assignment-queue`. SCRUM-93 and SCRUM-48 are in flight on their own branches above this one; all three touch `events/services.py`, so expect mechanical conflicts in its append regions whenever these are stacked.

## Global Constraints

- **British spelling** in code and API (`organiser`, `serialise`).
- **Module boundaries.** A module never imports another module's `models`; it calls the other module's `services.py`. Import `Role` and the role groups from `app.modules.auth.permissions`. `app/common/` never imports from `app/modules/`.
- **Layers.** `routes.py` thin: parse → call service → serialise. Services raise `AppError` subclasses from `app.common.errors`; routes never build error responses.
- **Auth:** `@requires_auth` / `@requires_role(Role.X)` from `app.common.decorators`. Never spell a role string by hand.
- **Not-found over forbidden:** a staff member reaching an event that is not theirs gets **404**, matching "no such request", so references cannot be probed (ADR-0012, ADR-0019, ADR-0034). Do not introduce a 403 for this.
- **Dates:** never `date.today()` or a naive `datetime.now()` (ruff DTZ blocks them).
- **Service signatures** take keyword-only `session: Session | None = None`, resolved with `resolve_session(session)`.
- **Helpers first**; **no repeated code**, in tests too; **no decorative tests**.
- **Every test module** sets `pytestmark = pytest.mark.scrum_96`; declare the marker in `pytest.ini` (`--strict-markers`).
- **Probably NO migration.** Task 2 decides: if AC5 is met by reusing an existing `NotificationKind`, this branch adds none. If it needs a new kind, it takes `0025` and must chain on whichever migration is below it at stack time — and then see the Postgres note below.
- **If a migration is added:** Postgres 18 is at `/opt/homebrew/opt/postgresql@18`. Replay `upgrade()` → `downgrade()` → `upgrade()` on a throwaway cluster and tear it down; do not sign a migration off by reading. On 2026-10-13 a sibling story's migration passed a careful read and then failed on a real cluster, twice.
- **Conventional Commit subjects** naming the story: `feat(SCRUM-96): ...`. **Never add a `Co-Authored-By` line or any AI/model attribution to a commit or PR.**
- Run from `backend/`:
  ```bash
  export PY=/Users/ernesttan/Desktop/SMU/Y3S1/SPM/SPM-Software-Project-Management-/backend/.venv/bin/python
  cd /Users/ernesttan/Desktop/SMU/Y3S1/SPM/spm-worktrees/SCRUM-96/backend
  ```
  Read files with Bash (`cat`, `sed -n`) if the Read tool is blocked outside the main repo.

## What already works

Verify each with a test that would go red if it broke, and add the test where it is missing. Write no new code for these.

| AC | Already delivered by | Where |
|---|---|---|
| AC4 "the previous assignment is kept in the event history" | SCRUM-87 writes `COORDINATOR_REASSIGNED` with the previous and new coordinator and their names; history is append-only | `events/services.py:1346` |
| AC4 "exactly one coordinator" | `coordinator_id` is a single FK that reassignment overwrites | `events/services.py` |
| AC4 "the previous coordinator loses access" | every assignment-scoped lookup goes through `_check_assigned_to` / `_assigned_to`, so overwriting the FK removes access everywhere at once | `events/services.py:943`, `:501` |
| AC5, two of three recipients | `_notify_about_assignment` tells the new coordinator (`COORDINATOR_ASSIGNED`) and the organiser (`REQUEST_ASSIGNED`) | `events/services.py:302` |

## Design decisions (the spec)

1. **Reassignment moves to the Lead, and only the Lead.** The route becomes `@requires_role(Role.EVENT_COORDINATOR_LEAD)` and the service's "are you this event's current coordinator?" check is replaced by "are you a Lead?" — which the decorator already proves, so the check is simply dropped. AC3 says *"Event Coordinators cannot reassign"*, so this is a replacement, not an addition. SCRUM-87's own ACs are superseded here; its change note says so.

2. **"Active event" is defined as `REASSIGNABLE_STATUSES`,** which already exists at `events/services.py:1282` as `{SUBMITTED, UNDER_REVIEW, AWAITING_CLARIFICATION, APPROVED, CONFIRMED}` with the comment "from submission until the event is over". AC1's "all active events under their supervision" uses exactly that set, renamed and re-sited so both the list and the reassignment guard read from one definition rather than two that can drift. Drafts are excluded (they are the organiser's private work) and completed, cancelled and rejected events are excluded (nothing left to coordinate). *(Judgement call: the ACs never define "active". Recorded in ADR-0041.)*

3. **"Under their supervision" means all of them.** The story's own Assumption says Release 1 has a single Lead supervising every coordinator, so AC1 needs no per-Lead filter.

4. **AC5's missing recipient is the previous coordinator.** Today the code deliberately does not tell them, with the comment *"The previous coordinator isn't told: only they may reassign, so they did this."* Under SCRUM-96 the Lead is the actor, so that rationale dies and the previous coordinator must be told. **Reuse `NotificationKind.REQUEST_ASSIGNED`** rather than adding a kind: it already means "this request's assignment changed", it is already sent to the organiser on the same event, and reusing it keeps this branch migration-free. A Postgres enum can never drop a value, so a new kind is a permanent cost to weigh against a clearer name. *(Judgement call, recorded in ADR-0041. If the team prefers a distinct `COORDINATOR_UNASSIGNED` kind, that is a migration and a follow-up ticket.)*

5. **AC6 closes a real gap that is live on `main`.** `GET /requests/<reference>/history` is `@requires_role(*INTERNAL_ROLES, Role.EVENT_ORGANISER)`, and `list_event_history` (`events/services.py:1806`) states *"Internal staff may see any event's history"*. So an Event Coordinator can read the history — decisions, clarifications, reassignments, field changes — of any non-draft event they are not assigned to. Every **write** path and every other **read** path is assignment-scoped; this is the only exception. AC6 ("view and manage only the events assigned to them", reworded on 2026-10-13 to add "view") makes it this story's job.

   **The fix is role-dependent, not blanket:** an Event Coordinator may read only their own event's history; the Lead, Venue Staff and Technical Support Staff keep access to any event's history, because their work spans events and no AC restricts them. `list_event_history` already takes `viewer_role`, so the scoping goes there beside the organiser's existing rule.

   This also means a reassigned-away coordinator loses history access, which AC4 wants.

6. **Nothing is renamed that SCRUM-87 still owns.** `reassign_coordinator` keeps its name and its history kind; only its caller's role and its guard change. The stale docstring sentences in `reassign_coordinator` and `assign_coordinator_to_request` that describe the old coordinator-driven flow are corrected as part of the change.

## Review Focus

Input classes the ACs imply but no happy path exercises. Each has its test in the owning task.

1. **An Event Coordinator calling the reassign route** — must be 403 from the decorator, with the service never reached. SCRUM-87's existing tests assert the opposite and must be updated, not deleted. (Task 1)
2. **The Lead reassigning an event that has no coordinator yet** — SCRUM-87 raises `RequestNotReassignableError` for that; it must still do so rather than silently assigning, because assignment is SCRUM-95's `/coordinator` route. (Task 1)
3. **The Lead reassigning an event to the coordinator who already holds it** — must stay a `ConflictError`. (Task 1)
4. **A coordinator fetching the history of an event assigned to someone else** — must be 404, and the same call by Venue Staff, Technical Support and the Lead must still succeed. (Task 3)
5. **An event in a terminal status (completed, cancelled, rejected) and a draft** — must not appear in the Lead's active-events list. (Task 2)

---

### Task 1: Only the Lead may reassign

**Files:**
- Modify: `backend/app/modules/events/routes.py` — `reassign_request` (at :307)
- Modify: `backend/app/modules/events/services.py` — `reassign_coordinator` (at :1346), `_coordinator_to_replace` (at :1307)
- Modify: `backend/pytest.ini`
- Test: `backend/tests/events/test_reassign_coordinator.py`, `test_reassign_coordinator_routes.py`, `test_reassign_coordinator_notifications.py` (all exist, marker `scrum_87`); create `backend/tests/events/test_lead_oversight.py` for the new behaviour

**Interfaces:**
- Consumes: `Role.EVENT_COORDINATOR_LEAD`, `reassign_coordinator`, `_event_request_for_staff`, `REASSIGNABLE_STATUSES`, `_notify_about_assignment`.
- Produces: `reassign_coordinator(actor_id, reference, payload, *, session=None) -> tuple[EventRequest, CoordinatorContact]` — same signature, now Lead-only, with the assigned-to-caller check removed.

- [ ] **Step 1: Declare the marker**

Add to `backend/pytest.ini`'s `markers` block, after the `scrum_95` line:

```
    scrum_96: tests for SCRUM-96 "Lead reassigns events and oversees coordinator assignments"
```

- [ ] **Step 2: Read what you are changing, in full**

```bash
sed -n '1280,1400p' app/modules/events/services.py   # REASSIGNABLE_STATUSES, _coordinator_to_replace, reassign_coordinator
sed -n '300,330p'   app/modules/events/services.py   # _notify_about_assignment
sed -n '305,330p'   app/modules/events/routes.py     # the reassign route
```

`_coordinator_to_replace` makes three checks in this order, and the order is asserted by existing tests: (1) no coordinator at all → `RequestNotReassignableError`; (2) caller is not the current coordinator → 404; (3) status not reassignable → `RequestNotReassignableError`. **Check (2) is the one that goes.** Checks (1) and (3) stay, in the same order.

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/events/test_lead_oversight.py` with `pytestmark = pytest.mark.scrum_96`, covering:

1. the Lead reassigns an event they do not coordinate, and it succeeds (the whole point of AC3);
2. **Review Focus 2** — the Lead reassigning an event with no coordinator still raises `RequestNotReassignableError`;
3. **Review Focus 3** — reassigning to the coordinator who already holds it is still a `ConflictError`;
4. a reassignment by the Lead still writes one `COORDINATOR_REASSIGNED` history entry carrying the previous and new coordinator ids and names, with `actor_id` set to the **Lead** (AC4);
5. an event in a non-reassignable status is still refused.

Use the existing fixtures: `saved_leads` (`tests/events/conftest.py:123`), `coordinator_of` (`:240`), `history_of` (`:193`), `set_status` (`:417`), `reassign` (`:538`). Read each before using it; do not write a second version of something that exists.

Then update the three SCRUM-87 test files for the superseding role change — **update, do not delete, and keep their `scrum_87` marker** so the old story's coverage stays traceable:
- `test_reassign_coordinator_routes.py`: the assertion that `allowed_roles == frozenset({"event_coordinator"})` becomes the Lead (**Review Focus 1**), and the "every other role is refused" parametrisation must now include `EVENT_COORDINATOR` among the refused and exclude the Lead. Follow the pattern in `test_lead_assignment_permissions.py`, which already does exactly this shape for a Lead-only route.
- `test_reassign_coordinator.py`: `test_only_the_events_own_coordinator_may_reassign_it` no longer describes the system. Replace it with a test named for the new rule — any Lead may reassign any reassignable event — rather than leaving a renamed shell.

- [ ] **Step 4: Run them to verify they fail**

```bash
$PY -m pytest tests/events/test_lead_oversight.py tests/events/test_reassign_coordinator_routes.py -q
```
Expected: FAIL — the route still allows only `EVENT_COORDINATOR`, so the Lead gets 403.

- [ ] **Step 5: Make the change**

In `routes.py`, change the decorator on `reassign_request` to `@requires_role(Role.EVENT_COORDINATOR_LEAD)`, and update its docstring to say the Lead reassigns.

In `services.py`, delete the `_check_assigned_to(actor_id, event_request)` call from `_coordinator_to_replace` and rename its `actor_id` parameter if it becomes unused there. Keep checks (1) and (3) and their order. Update `reassign_coordinator`'s docstring: it is the Lead's action now, the status list it names is stale (the code allows five statuses — say which), and the sentence about the previous coordinator not being told is corrected in Task 2. Also correct the stale sentence in `assign_coordinator_to_request` (at :1956) that says a move of an already-assigned request "is a reassignment, which the coordinator does themselves through SCRUM-87's `/reassign`".

- [ ] **Step 6: Run, then lint and the full suite**

```bash
$PY -m pytest tests/events -q
$PY -m ruff format . && $PY -m ruff check . && $PY -m pytest -q
```

Any other test that assumed a coordinator may reassign will fail here. Fix each by updating it to the new rule, and **list every test you touched in your report** — a silently rewritten assertion is how a regression hides.

- [ ] **Step 7: Commit**

```bash
git add backend/pytest.ini backend/app backend/tests
git commit -m "feat(SCRUM-96): move reassignment from any coordinator to the Lead"
```

---

### Task 2: Tell the coordinator who lost the event, and give the Lead their two views

**Files:**
- Modify: `backend/app/modules/events/services.py` — `_notify_about_assignment` (at :302), and a new section for the two lists
- Modify: `backend/app/modules/events/routes.py`
- Test: `backend/tests/events/test_lead_oversight.py` (append); `backend/tests/events/test_reassign_coordinator_notifications.py` (update)

**Interfaces:**
- Consumes: `_raise_notifications(recipient_ids, event_request, kind, session, *, detail=None)` (at :269); `NotificationKind.REQUEST_ASSIGNED`; `_list_event_requests_newest_first` (at :438); `_assigned_to` (at :501).
- Produces: `ACTIVE_STATUSES: frozenset[EventRequestStatus]`; `list_active_requests(*, session=None) -> list[EventRequest]`; `list_requests_for_each_coordinator(*, session=None) -> list[CoordinatorWorkload]`; the frozen dataclass `CoordinatorWorkload(coordinator_id: int, coordinator_name: str, assigned: list[EventRequest])`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/events/test_lead_oversight.py`:

**For AC5** — after the Lead reassigns, three notifications exist for that event: the new coordinator's `COORDINATOR_ASSIGNED`, the organiser's `REQUEST_ASSIGNED`, and the **previous coordinator's** `REQUEST_ASSIGNED`. Assert the previous coordinator is among the recipients and that there are exactly three. Use `notifications_of` (`tests/conftest.py:439`) or `detailed_notifications_of` / `assignment_notices_of` (`tests/events/conftest.py:371`, `:344`) — read them and pick the one that exposes recipients.

**For AC1** — `list_active_requests` returns events in each of the five active statuses with their coordinator and status, and (**Review Focus 5**) excludes drafts, completed, cancelled and rejected events. Assert on ids, not on list length alone.

**For AC2** — `list_requests_for_each_coordinator` returns one entry per coordinator who holds at least one active event, carrying that coordinator's name and their events. Cover a coordinator with two events, and assert a coordinator with none does not appear (or does appear with an empty list — **decide and assert one; say which you chose and why in your report**).

Then update `test_reassign_coordinator_notifications.py`: its assertion that nobody but the new coordinator and the organiser is told is now wrong. Rewrite it to the new rule and keep its `scrum_87`/`scrum_39` markers.

- [ ] **Step 2: Run them to verify they fail**

```bash
$PY -m pytest tests/events/test_lead_oversight.py -q
```
Expected: FAIL — no `list_active_requests`, and only two notifications.

- [ ] **Step 3: Add the previous coordinator to the notification**

`_notify_about_assignment` is shared by SCRUM-87's reassignment and SCRUM-95's first assignment, and a first assignment has no previous coordinator. Add an optional previous-coordinator parameter rather than a second near-copy of the function, and notify them with `REQUEST_ASSIGNED` only when there is one. Delete the now-false comment "The previous coordinator isn't told: only they may reassign, so they did this." A failure to write notifications must still be rolled back and logged, not raised (ADR-0015) — keep that behaviour.

- [ ] **Step 4: Define "active" once, and add the two lists**

Move the definition of the reassignable/active statuses so that one frozenset serves both. Name it `ACTIVE_STATUSES`, place it where `REASSIGNABLE_STATUSES` is now (`:1282`), keep its explanatory comment, and have the reassignment guard read from it. **Do not leave two frozensets with the same members** — that is the drift this decision exists to prevent. If other code references `REASSIGNABLE_STATUSES` by name, either keep that name as the single definition and use it for the list, or rename every reference; say which you did.

Then add `list_active_requests` and `list_requests_for_each_coordinator` with the `CoordinatorWorkload` dataclass, following `list_unassigned_requests` (`:1899`) for query shape and `CoordinatorContact` for how a coordinator's name is resolved without exposing a user id.

- [ ] **Step 5: Add the two routes**

Beside `list_unassigned` (`routes.py:188`), both `@requires_role(Role.EVENT_COORDINATOR_LEAD)`:

```python
@bp.get("/requests/active")        # AC1
@bp.get("/coordinators/workload")  # AC2
```

Match the existing list routes' response shape — read `_event_list_body` (`routes.py:83`) and use it rather than inventing a second envelope. Add permission tests for both in the file that covers Lead-only routes, following `test_lead_assignment_permissions.py`'s parametrised pattern.

- [ ] **Step 6: Run, lint, full suite, commit**

```bash
$PY -m pytest tests/events -q
$PY -m ruff format . && $PY -m ruff check . && $PY -m pytest -q
git add backend/app backend/tests
git commit -m "feat(SCRUM-96): tell the previous coordinator and show the Lead every active event"
```

---

### Task 3: Close the history read path (AC6)

**Files:**
- Modify: `backend/app/modules/events/services.py` — `list_event_history` (at :1806)
- Test: `backend/tests/events/test_lead_oversight.py` (append), or the existing history test file if one covers `list_event_history` — check first

**Interfaces:**
- Consumes: `list_event_history(viewer_id, reference, *, viewer_role, session=None)`, `_event_request_by_reference`, `_assigned_to`, `_event_request_for_staff`.
- Produces: the same signature, now scoping an Event Coordinator to their own events.

- [ ] **Step 1: Confirm the gap for yourself**

```bash
sed -n '1806,1860p' app/modules/events/services.py
sed -n '365,382p'   app/modules/events/routes.py
grep -rn "list_event_history" tests/ | head
```

The docstring says "Internal staff may see any event's history". Confirm there is no assignment check, and find the existing tests so you extend them rather than duplicating.

- [ ] **Step 2: Write the failing tests**

**Review Focus 4**, four cases in one parametrised test plus one negative:
- an Event Coordinator reading the history of an event assigned to **them** succeeds;
- an Event Coordinator reading the history of an event assigned to **someone else** raises `NotFoundError` with the same message an unknown reference gives (assert the message, so the 404 really is indistinguishable);
- the **Lead**, **Venue Staff** and **Technical Support Staff** each still read that same event's history successfully;
- the **Event Organiser**'s existing rule is unchanged — their own organisation's event still works, and the internal-only entries are still filtered (do not re-test `_shown_to_organiser`'s filtering itself, which SCRUM-33 owns; just prove you did not break the organiser path).

- [ ] **Step 3: Scope it**

In `list_event_history`, look the event up with `belongs_to=_assigned_to(viewer_id)` when `viewer_role is Role.EVENT_COORDINATOR`, and with the existing staff lookup for every other internal role. Keep the organiser branch exactly as it is. Update the docstring: internal staff may see any event's history **except** an Event Coordinator, who may see only their own assigned events (AC6, and SCRUM-24 AC10).

Do not touch the route's `@requires_role(*INTERNAL_ROLES, Role.EVENT_ORGANISER)` — the role list is right; it is the service that must scope.

- [ ] **Step 4: Run, lint, full suite**

```bash
$PY -m pytest tests/events -q
$PY -m ruff format . && $PY -m ruff check . && $PY -m pytest -q
```

Any existing test that reads another coordinator's history will now fail. That is the bug being fixed — update the test to the new rule and report it.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests
git commit -m "fix(SCRUM-96): scope an event's history to the coordinator it is assigned to"
```

---

### Task 4: ADR-0041, the route table, and the coverage gate

**Files:**
- Create: `docs/adr/0041-lead-oversight-and-reassignment.md`
- Modify: `README.md` (route table); `docs/adr/0021-*.md` and `docs/adr/0034-*.md` if they state the superseded rule — check and mark them superseded in part, following how `docs/adr/0026` was marked by SCRUM-24

- [ ] **Step 1: Verify the already-met criteria**

Confirm, with the test names, that AC4's three parts and AC5's two existing recipients are covered by tests that would go red if they broke (see "What already works"). Report the test names; write a test only where one is genuinely missing.

- [ ] **Step 2: Write ADR-0041**

Follow `docs/adr/0035-venue-booking-requests.md`'s shape exactly. Record the six decisions in this plan's "Design decisions" section with their reasoning, then add:

- **Supersedes:** SCRUM-87's actor (ADR-0021 if that is where it lives — check) and the part of ADR-0034 that describes who may reassign. Mark those ADRs as superseded in part, as SCRUM-24 did to ADR-0026.
- **Deferred:** a distinct `COORDINATOR_UNASSIGNED` notification kind, if the team prefers one over reusing `REQUEST_ASSIGNED` (decision 4) — a migration and a follow-up ticket.
- **Defaults to review (not agreed with the team):** decision 2 (what "active" means), decision 4 (reusing `REQUEST_ASSIGNED` for the previous coordinator), the Task 2 Step 1 choice about whether a coordinator with no active events appears in the workload list, and anything the implementers flagged.
- **A note that AC6 fixed a live gap on `main`:** before this story, an Event Coordinator could read any non-draft event's history. Record it so the team knows it was a defect, not a new restriction.

- [ ] **Step 3: Add the two routes to the README table**

```
| `GET /api/events/requests/active` | `event_coordinator_lead` — every active event with its coordinator and status |
| `GET /api/events/coordinators/workload` | `event_coordinator_lead` — each coordinator's current assignments |
```

Match the table's existing column format, and update the existing `/requests/<reference>/reassign` row to say the Lead, and the `/requests/<reference>/history` row to note that a coordinator sees only their own.

- [ ] **Step 4: Run the full definition-of-done checks**

```bash
$PY -m ruff format . && $PY -m ruff check .
$PY -m pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=xml -q
$PY -m diff-cover coverage.xml --compare-branch=origin/feat/SCRUM-95-lead-assignment-queue --fail-under=100
```

Expected: lint clean, every test passing, `diff-cover` 100%. Then read the `Missing` column for `events/services.py` and `events/routes.py` — `diff-cover` cannot see branches, so any `a->b` on a line this branch added is a gap to test or to justify with `# pragma: no cover - <reason>`. The role branching in `list_event_history` is the likeliest place to miss one.

- [ ] **Step 5: Commit**

```bash
git add docs README.md
git commit -m "docs(SCRUM-96): record the Lead oversight decisions as ADR-0041"
```

---

## After the last task

Run the `review-checklist` skill over the whole branch (`git diff feat/SCRUM-95-lead-assignment-queue...HEAD`), fix every **must** and **should**, re-run Task 4 Step 4, and report:

- the AC traceability table, naming the test for each;
- every test you changed that previously asserted the old rule, and why;
- every check, passed or failed;
- every coverage gap with its reason;
- the judgement calls for the team to confirm or overturn.
