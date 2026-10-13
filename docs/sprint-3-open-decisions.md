# Sprint 3 — decisions awaiting a product call

Three stories were built on 2026-10-13: **SCRUM-93** (book several venues for one event,
PR #66), **SCRUM-48** (record the outcome of an equipment review, PR #65) and **SCRUM-96**
(Lead reassigns events and oversees coordinator assignments, PR #67).

Their acceptance criteria left a number of points unsettled. Rather than stall, each was
decided, recorded in the owning ADR, and listed under **"Defaults to review"** in its PR
description. This file collects them in one place so the team or the customer can overturn any
of them in a single pass instead of finding them spread across three reviews.

**How to use it.** Each entry says what was decided, why, and **what it costs if the decision is
wrong** — that last line is the one to read when deciding whether to spend time on it. Nothing
here blocks a merge; every item is live behaviour that can be changed later, most of them
cheaply.

Full reasoning lives in [ADR-0039](adr/0039-venue-arrangements.md),
[ADR-0040](adr/0040-equipment-review-outcome.md) and
[ADR-0041](adr/0041-lead-oversight-and-reassignment.md).

> **Those three ADRs are not on `main` yet** — each arrives with its own story's pull request
> (ADR-0039 with #66, ADR-0040 with #65, ADR-0041 with #67), so the links above only resolve
> once those merge. This file is deliberately readable without them.

---

## 1. Needs a product or customer decision

### 1.1 Does a rejected venue arrangement block event confirmation? — **the sharpest one**

**Status: genuinely undecided. SCRUM-43 and SCRUM-49 must agree before either ships.**

SCRUM-49 refuses confirmation until *"every active arrangement is approved"*, and SCRUM-97
gates Safety Review on the same. SCRUM-75, SCRUM-49 and SCRUM-97 each say only *"withdrawn and
cancelled arrangements are ignored"* — none of them says what a **rejected** arrangement does.

SCRUM-93 shipped a code comment telling SCRUM-43's implementer to retire `rejected` alongside
`cancelled`. That was removed during review, because if it were followed an event with one
approved and one rejected venue would pass **both** gates — contradicting SCRUM-49's own
*"unfulfillable arrangements move the event to Rejected"* and SCRUM-43's *"rejecting it releases
the venue immediately"*. Today `rejected` is **not** retired, so a rejected arrangement still
counts as active and still blocks confirmation.

**Cost if wrong:** if the team wants a rejected arrangement to be ignorable, SCRUM-43 and
SCRUM-49 will both need changing, and an event whose venue was rejected can currently never be
confirmed without the coordinator withdrawing that arrangement first.

### 1.2 Can an equipment outcome be recorded on a dead event?

Technical Support can record an outcome on an event in **any** non-draft status, including
rejected, cancelled and completed — and the coordinator is still notified. No AC forbids it, and
no status guard was added.

**Cost if wrong:** coordinators get notifications about events that are over or abandoned.

### 1.3 Is a note required for a *partially fulfilled* outcome?

**Yes, as built.** AC3 requires a reason only when *nothing* is available; AC1 shows a note
beside a partial outcome without saying it is mandatory. A note is now required whenever less
than the whole request is provided, and never when it is met in full.

**Cost if wrong:** Technical Support is forced to type a note in a case the customer intended to
be optional.

### 1.4 Is the coordinator notified of *every* outcome, or only an unavailable one?

**Every outcome, as built.** AC3 names the notification only for the nothing-available case, but
SCRUM-97's own team assumption says *"Any outcome recorded by Technical Support, including
partially fulfilled or unavailable, counts as their decision; the coordinator is notified of it
(SCRUM-48)"*.

**Cost if wrong:** more notification noise for coordinators than the customer asked for.

### 1.5 Does an event with no equipment count as "all outcomes recorded"?

**Yes — vacuous truth, as built.** `all_outcomes_recorded()` returns `True` when an event has no
equipment lines at all, so SCRUM-97's and SCRUM-49's gates will pass for equipment-free events.

**Cost if wrong:** if those gates should instead require *some* equipment decision, each needs
to add its own has-equipment check.

### 1.6 What does an Event Organiser see of an equipment outcome?

**The line's status only** (`fulfilled` / `partially_fulfilled` / `unavailable`), not the
quantity provided, the note or the reviewer's name. Masking the status too would have changed
SCRUM-37's existing output, and the status is the least sensitive part.

**Cost if wrong:** organisers either see less than intended, or — if the status should also be
hidden — see internal review detail.

### 1.7 Can a coordinator invalidate a recorded outcome by editing the line?

**Partly.** Lowering a line's quantity *below* a recorded `provided_quantity` is refused with a
400. **Raising** the quantity, or **removing** the line, is still allowed: raising leaves the
status reading `fulfilled` beside a positive shortfall, and removing discards the outcome
entirely. Changing SCRUM-37's edit rules further was judged a scope change.

**Cost if wrong:** a coordinator can silently invalidate Technical Support's decision, and
SCRUM-97's gate would then pass on stale data.

### 1.8 Should a submitted-but-unassigned event appear in two of the Lead's lists?

**Yes, as built.** `ACTIVE_STATUSES` includes `submitted`, and AC1 says *all* active events, so
an event nobody holds yet shows in both the unassigned queue and the active list. The two serve
different purposes — one is a to-do, the other oversight — but the overlap is visible.

**Cost if wrong:** the Lead sees the same item twice and may act on it twice.

### 1.9 Should idle coordinators appear in the Lead's workload view?

**No, as built.** The workload list is derived from events, so a coordinator with no active
events is simply absent. Listing idle coordinators needs a cross-module user lookup that no AC
asks for.

**Cost if wrong:** the Lead cannot see who is free, which is arguably the point of a workload
view.

### 1.10 How is the previous coordinator told they lost an event?

By a **`detail` string on the existing `REQUEST_ASSIGNED` notification**, not a new
`COORDINATOR_UNASSIGNED` kind. This keeps SCRUM-96 migration-free. A Postgres enum can never
drop a value, so a new kind is a permanent cost.

Worth knowing: the first implementation gave the previous coordinator the **organiser's**
wording — *"an Event Coordinator has been assigned to your event request"* — which never told
them they had lost anything. A reviewer caught it.

**Cost if wrong:** the notice's wording lives in a detail string rather than a typed kind, so a
client cannot branch on it. Adding the kind later is a migration.

### 1.11 Can the venue or the period of an arrangement be changed?

**No.** Together they *are* the slot Venue Staff were asked about, so changing either is a
different ask: withdraw the arrangement and raise another. Only the purpose, expected occupancy,
required layout and justification can change, and only while the arrangement is Pending.

**Cost if wrong:** coordinators must withdraw and re-raise to move a booking, which costs them a
step and loses the original arrangement's place in Venue Staff's queue.

### 1.12 Can a coordinator act on an arrangement of a dead event?

**Yes.** There is no event-status guard on withdraw, change or cancel-all, so a coordinator can
withdraw an arrangement of a Completed, Cancelled or Rejected event — whereas *raising* one
requires the event to be Approved. Withdrawing from a cancelled event is sensible cleanup, which
is why it was left open, but it is asymmetric and unrecorded in the ACs.

**Cost if wrong:** an inconsistency between raising and retiring, and history entries written
against events that are over.

### 1.13 How is a required layout cleared?

**By sending `required_layout` as `null`.** Nothing else on an arrangement can be cleared —
every other field treats "absent" as "leave alone". This mirrors `update_equipment_line`'s
documented behaviour (*"`notes` is cleared only when sent as `null`"*).

**Cost if wrong:** trivial — the field becomes set-once, or the pattern extends to other fields.

### 1.14 What does "active event" mean?

**The five statuses from submission until the event is over**: `submitted`, `under_review`,
`awaiting_clarification`, `approved`, `confirmed`. Drafts are the organiser's private work;
completed, cancelled and rejected events have nothing left to coordinate. The constant
`REASSIGNABLE_STATUSES` was renamed `ACTIVE_STATUSES` so one definition serves both the Lead's
list and the reassignment guard rather than two that can drift.

**Cost if wrong:** the Lead's oversight list shows the wrong set, and the reassignment guard
changes with it, since they now share one definition.

---

## 2. Engineering calls, recorded for a reviewer rather than a decision

These are defensible and already in the ADRs; they are listed so a reviewer is not surprised.

| # | Call | Cost if wrong |
|---|---|---|
| 2.1 | Migration `0023`'s downgrade **deletes** withdrawn arrangements rather than reverting them to `pending`, and says so — reverting would resurrect retired work as live Pending requests and can violate the partial unique index. | A downgrade loses withdrawn arrangements. Downgrade is already lossy elsewhere. |
| 2.2 | That downgrade **drops and re-creates** `uq_venue_booking_requests_pending` around the enum rebuild, because its `WHERE status = 'pending'` predicate is otherwise deparsed against the renamed type. Found by replaying on a real Postgres cluster, not by reading. | None — reproduced and verified twice independently. Anyone adding a value to this enum later hits the same trap. |
| 2.3 | Migration `0024`'s revision id is **`0024_add_equipment_outcome`**, not its file name — `alembic_version.version_num` is `VARCHAR(32)` and the longer id fails on a real database. | Later migrations must chain on the short id. SCRUM-97/49 rebases must use it. |
| 2.4 | `cancel_all_arrangements`'s single-commit rollback path is **unreachable today**, because only `pending` arrangements are ever active. It becomes reachable when SCRUM-43 adds `approved`. | A rollback path ships untested until SCRUM-43. The guard itself is covered through `withdraw_arrangement`. |
| 2.5 | The migration/model enum drift test was loosened from `==` to `<=` for `booking_request_status`, matching the two assertions above it in the same file. | A model status with no migration behind it would pass. Pre-existing for two other enums; the `PREVIOUS_*_VALUES` tuples are now the only thing pinning all three. |
| 2.6 | The Lead's active-events list returns a small `ActiveRequest` wrapper rather than bare event rows, because AC1 needs the coordinator's name and modules may not cross-join ORM relationships. | A later story reading the plan's signature must adapt to the wrapper. |
| 2.7 | `.superpowers/` was added to this clone's `.git/info/exclude`. Local to one machine, nothing committed, but it affects every worktree there. | None to the repository. |

---

## 3. Follow-ups that are not decisions

Already listed under **"Tickets to open"** in the three PRs; repeated here so nothing is lost:

- **No test asserts that the union of all migrations' enum values equals the model enum**, so a
  model value with no migration behind it would pass. Pre-existing for the history and
  notification kinds; SCRUM-93 widens it to a third enum.
- **Seven new endpoints across the three stories have no frontend mock handler or integration
  test** (`backend/CONVENTIONS.md` §14). Nothing is broken — no frontend `it.todo` waits on them
  — but the mocked app is now more permissive than the backend, and SCRUM-96 additionally makes
  `GET /requests/<reference>/history` return 404 for an unassigned coordinator, which the mock
  does not model.
- **Dead test code** in `backend/tests/events/test_lead_oversight.py`: three orphaned lines and
  one stale module-docstring sentence. Lint stays green.
- **`NON_LEAD_ROLES` has a third copy** in `tests/events/test_lead_assignment_permissions.py`,
  inherited from SCRUM-95.
- **ADR-0021 still mentions `REASSIGNABLE_STATUSES`** and has an unmarked "Revisit when" clause
  about who may reassign.
- **ADR numbers 0033 and 0038 are unclaimed holes** in the index. 0038 is reserved for SCRUM-75;
  confirm nobody holds 0033.
- **Does `docs/superpowers/` belong in the repository?** PRs #65, #66 and #67 each commit agent
  planning documents there. The directory is not tracked on `main`, not in `.gitignore`, and not
  described in `README.md` or `CLAUDE.md`. One decision either way.

---

## 4. Two requirements gaps outside these three stories

Found while planning, and still unresolved:

- **"Active venue arrangement" is defined in no ticket.** SCRUM-75 says an event is multi-venue
  when it has *"more than one active venue arrangement (withdrawn and cancelled arrangements are
  ignored)"*, but no story defines `active`, `withdrawn` or `cancelled` for an arrangement.
  SCRUM-93 now implements the concept; the definition should be written into SCRUM-93 or
  SCRUM-75 so the code and the ticket agree.
- **SCRUM-98 cites SCRUM-99**, which was moved out to Sprint 4. Its AC reads *"Reject returns the
  event to Planning, the same as Request Changes (see SCRUM-99)"* — a cross-sprint dependency.

---

## 5. Appendix — mechanical rulings, no decision needed

Roughly twenty further rulings were made during implementation that need nobody's attention:
an import position that `ruff` decides, a `diff-cover` invocation that is a binary rather than a
module, a test-file path named wrongly in a plan, a one-character test-name typo, docstring
reflow, a type annotation on a test helper, and several plan statements corrected because they
described fields or files that do not exist. Each is recorded in the per-story ledgers and none
changes behaviour.

Three are worth one line each, because they were plan defects that a reviewer caught rather than
preferences:

- A plan asserted *"the migration cannot be executed here (no Postgres)"*. False — Postgres 18
  was installed, a reviewer replayed the migration on it, and found two real defects (2.1, 2.2).
- A test meant to prove "a refused change leaves the row untouched" called `expire_all()`, which
  discarded the unflushed values, so it passed whether or not the code was correct.
- A test meant to prove ordering passed with the `order_by` removed, because the fixture inserted
  rows in the order being asserted.

All three were repaired and the branch was then swept with nine behaviour mutations.
