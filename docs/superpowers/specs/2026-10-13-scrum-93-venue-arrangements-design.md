# SCRUM-93 — Book several venues for one event

- **Date:** 2026-10-13
- **Story:** [SCRUM-93](https://smu-team-uu78imq6.atlassian.net/browse/SCRUM-93) (To Do, last
  edited 2026-10-13 13:16 SGT)
- **Branch:** `feat/SCRUM-93-venue-arrangements`, stacked on
  `feat/SCRUM-95-lead-assignment-queue`
- **Migration:** `0023`
- **Marker:** `scrum_93`

## Intent

One event uses several venues at once — a conference with an auditorium and breakout rooms —
planned as a single event. The coordinator must be able to change, withdraw or cancel one
venue's arrangement without disturbing the others.

The story's real value to the sprint is narrower than its title suggests. Most of it already
works, and the piece that does not is the piece three other stories are blocked on: there is
no way to retire one arrangement, so there is no such thing as an **active** arrangement, and
SCRUM-75, SCRUM-49 and SCRUM-97 all now depend on that word.

## What already works

SCRUM-42 (code complete, PR #58) built the arrangement in all but name. Verify each with a
test that would go red if the behaviour broke; add the test where it is missing. Write no new
code for these.

| AC | Already delivered by | Where |
|---|---|---|
| AC1 several arrangements, same or overlapping times | SCRUM-42; only an exact duplicate is refused, by a partial unique index over Pending rows | `venue/models.py` `uq_venue_booking_requests_pending` |
| AC2 purpose, occupancy, layout, defaulted from the event | SCRUM-42 | `raise_booking_request`, ADR-0035 §4 |
| AC3 suitability per arrangement, not per event | SCRUM-42 | `_venue_is_suitable`; `test_suitability_uses_the_requests_occupancy_not_the_events` |
| AC4 *"different venues do not conflict with each other"* | `_booking_holds_venue` filters on `venue_id`, so cross-venue conflict is impossible by construction | `venue/services.py` |
| AC5 *"listed on the event record"* | SCRUM-42's `GET /api/venues/events/<reference>/booking-requests` | ADR-0035 §11 |

## What this story builds

### 1. Vocabulary: an arrangement is a `VenueBookingRequest`

An "arrangement" is the `VenueBookingRequest` row, and later the `Booking` it becomes. No new
table and no rename: `venue_booking_requests` is built on by SCRUM-42, SCRUM-45 and SCRUM-95,
and renaming it would churn three stacked branches to buy a synonym. The ADR records that the
two words mean the same thing, so a later reader does not go looking for a missing model.

### 2. One new status, and the `active` predicate

Migration `0023` adds **`withdrawn`** to `booking_request_status` — and only that. Per
ADR-0035 §3 a value is added when it has code, and `pending` is the only status any code path
can reach today: `approved`, `rejected` and `on_hold` arrive with SCRUM-43 and SCRUM-75.
Adding `cancelled` here would be a value nothing can produce and no test could reach, which
the project's full-branch-coverage rule would then force a `pragma` around.

`downgrade()` must unwind the added value, not just revert the column: Postgres cannot drop a
value from an enum, so the downgrade recreates the type. CI replays downgrade → upgrade.

The predicate is the deliverable other stories wait on, and it is phrased as an exclusion so
that it keeps being correct as statuses are added:

```python
#: Statuses that take an arrangement out of an event's venue count. SCRUM-43 adds
#: ``CANCELLED`` and ``REJECTED`` here; ``ON_HOLD`` stays active, which is what
#: SCRUM-75's "more than one active venue arrangement" needs.
RETIRED_REQUEST_STATUSES = frozenset({BookingRequestStatus.WITHDRAWN})
```

A one-member frozenset rather than `status is not WITHDRAWN`, because this set is the seam
SCRUM-43, SCRUM-75 and SCRUM-49 extend; the comment says how it grows.

Expose in `venue/services.py`:

- `list_active_arrangements(event_id, *, session=None) -> list[VenueBookingRequest]`
- `count_active_arrangements(event_id, *, session=None) -> int` — SCRUM-75's multi-venue test

### 3. Withdraw (AC6)

AC6 says *"changing, withdrawing or cancelling one arrangement leaves the event's other
arrangements untouched"*. It defines neither word, and only one of them can be built now:

| Action | From | To | Status |
|---|---|---|---|
| **Withdraw** | `pending` | `withdrawn` | **this story** — the coordinator retracts an arrangement before Venue Staff decide it |
| **Cancel** | `approved` | `cancelled` | **SCRUM-43** — ending an arrangement Venue Staff already approved needs `approved` to exist first |

So AC6's "cancelling" is deferred, with SCRUM-43 named as its owner in the ADR, following
ADR-0035 §13's pattern of listing each deferred criterion against the story that takes it.
Withdrawing is the whole of AC6 that is reachable today.

Withdrawing an arrangement that is not pending is a `409` naming its current status, following
`raise_booking_request`'s precedent for a wrong-status event. Only the event's assigned
coordinator may; another coordinator gets `404`, as ADR-0035 §6 established, so references
cannot be probed.

It must not touch the event's other arrangements — AC6's core promise, and the thing to test
explicitly: withdraw one of three, assert the other two are unchanged.

### 4. Cancel every arrangement (AC6)

AC6 allows one exception to "leave the others untouched": *"unless the coordinator explicitly
chooses to cancel all of them"*. That is one call, not a loop the client writes, so the intent
is explicit and recorded once in history.

It retires every **active** arrangement, which today means withdrawing every pending one, and
is a no-op returning an empty list when the event has none. The route and service keep AC6's
own word — `cancel-all` / `cancel_all_arrangements` — so that SCRUM-43 widens what it retires
without renaming a published endpoint.

### 5. Change an arrangement (AC6)

A `pending` arrangement's `purpose`, `expected_occupancy`, `required_layout`, `starts_at` and
`ends_at` may change, by its assigned coordinator. Once decided it may not: changing it would
silently void Venue Staff's decision. Partial update, shaped like
`events/services.py::update_equipment_line` — only the fields sent change.

A change re-runs both checks the original raise ran, against the new values:

- AC3 suitability, and AC7's justification requirement when the new occupancy or layout no
  longer suits the venue;
- SCRUM-42 AC2's operating-hours check when the period changes.

Reuse `_require_within_opening_hours` and `_venue_is_suitable` as they stand. The venue itself
cannot change — that is a different arrangement, raised separately and withdrawn here.

### 6. History (not an AC)

Following ADR-0035 §8, which added `venue_booking_requested` for the same reason: the team
asked that arrangement changes be traceable on the event. Three `EventHistoryKind` values,
written in the same commit as the change they record, so there is never a change without its
entry:

| Kind | `details` |
|---|---|
| `venue_arrangement_changed` | `venue_booking_request_id`, `venue_id`, and each changed field with its previous and new value (dates as ISO strings, as SCRUM-33's `field_changed` does) |
| `venue_arrangement_withdrawn` | `venue_booking_request_id`, `venue_id` |

`actor_id` is the coordinator in both. Migration `0023` adds the kinds alongside the status.
SCRUM-43 adds `venue_arrangement_cancelled` with the transition that writes it.

### 7. Routes

On SCRUM-42's existing path, all `@requires_role(Role.EVENT_COORDINATOR)`:

| Route | Does |
|---|---|
| `PATCH  /api/venues/events/<reference>/booking-requests/<id>` | change a pending arrangement |
| `POST   /api/venues/events/<reference>/booking-requests/<id>/withdraw` | withdraw it |
| `POST   /api/venues/events/<reference>/booking-requests/cancel-all` | retire every active one |

SCRUM-43 adds `<id>/cancel` beside them when an arrangement can be approved.

A verb sub-path matches the codebase's own precedent (`review_request`, `decide_request`,
`complete_request`). Routes stay thin: parse, call the service, serialise.

## Out of scope, with owners

| Deferred | Owner |
|---|---|
| Conflict detection between arrangements for the same venue | SCRUM-44 |
| `on_hold` in AC5 and AC7 | SCRUM-43, SCRUM-75 |
| AC6's *"cancelling"*: the `cancelled` status and the `approved` → `cancelled` transition | SCRUM-43, where `approved` first exists |
| Releasing a confirmed `Booking` when its arrangement is cancelled | SCRUM-43 — no `Booking` row is written by any code path yet |
| Notifying anyone about a change, withdrawal or cancellation | SCRUM-50 |

## Why arrangements keep a status instead of being deleted

Equipment lines are hard-deleted (`remove_equipment_line`). Arrangements must not be: SCRUM-75
defines a multi-venue event as one with *"more than one active venue arrangement (withdrawn and
cancelled arrangements are ignored)"*, which requires retired arrangements to still exist in
order to be ignored. SCRUM-94 AC5 likewise expects an expired hold to stay visible in history.

A withdrawn row also drops out of `uq_venue_booking_requests_pending`, because that index
covers `status = 'pending'` only — so withdrawing frees the slot and the coordinator can raise
the same venue and period again. That falls out of ADR-0035 §2 with no new code, and is worth
a test.

## Judgement calls to review at the end

Recorded here and in the ADR rather than settled silently:

1. **Withdraw vs cancel** split by the arrangement's status, leaving cancel to SCRUM-43 (§3).
   The ACs define neither word, and this is the reading under which both are needed.
2. **AC6's "cancelling" is deferred rather than built against an unreachable status** (§3).
   The alternative was to add `cancelled` now and `pragma`-exclude code no test can reach.
3. **A decided arrangement cannot be changed** (§5); the ACs do not say when changing stops
   being allowed.
4. **The venue cannot be changed** on an existing arrangement (§5) — that is a different
   arrangement, raised separately.
5. **`cancel-all` keeps AC6's word** although today it only withdraws (§4), so SCRUM-43 need
   not rename a published route.
6. **No notifications.** AC6 asks for none and SCRUM-50 owns them, but a coordinator
   withdrawing an arrangement Venue Staff have been told about arguably ought to tell them.

## Testing

Tests first, from the ACs, seen failing. Marker `scrum_93`, declared in `pytest.ini`.

| File | Covers |
|---|---|
| `tests/venue/test_venue_arrangements.py` | withdraw, its status guard, siblings untouched, cancel-all, the active predicate and counts |
| `tests/venue/test_venue_arrangement_changes.py` | partial change, the re-run suitability/justification and opening-hours checks, the decided-arrangement guard, history details |
| existing `tests/venue/test_booking_requests.py` | add the AC1/AC2 coverage gaps found while verifying the table above, and the re-raise-after-withdraw case |

Permission tests call the view through `app.test_request_context`, as `tests/conftest.py` does
for every other route. Full line **and** branch coverage of changed code; `diff-cover` compares
against `origin/feat/SCRUM-95-lead-assignment-queue`, the branch below in the stack.

## Definition of done

The project's five steps in `CLAUDE.md`, in order, ending with the `review-checklist`
self-review and a report of what it found, what was fixed, and every coverage gap with its
reason.
