# ADR-0039: A venue arrangement is a venue booking request; a coordinator can change, withdraw or retire all of an event's arrangements, and the retired ones stay on record

- **Status:** Accepted
- **Date:** 2026-10-13
- **Story:** SCRUM-93 Book several venues for one event

## Context
SCRUM-93 lets one event use several venues at once, such as a conference with an auditorium and breakout rooms, planned as a single event. The coordinator must be able to change, withdraw or cancel one venue's arrangement without disturbing the others. SCRUM-42 ([ADR-0035](0035-venue-booking-requests.md)) already delivers most of this: AC1 to AC5 hold by construction, and tests pin each one. What was missing is any way to retire one arrangement, so there was no such thing as an **active** arrangement, and SCRUM-75, SCRUM-49 and SCRUM-97 all depend on that word. The ACs also leave open what "changing", "withdrawing" and "cancelling" mean, when a change stops being allowed, and whether a change may move the venue or the period.

## Decision
1. **An arrangement is a `VenueBookingRequest`.** There is no new table and no rename, because SCRUM-42, SCRUM-45 and SCRUM-95 all build on `venue_booking_requests`. The two words mean the same row (and later the `Booking` it becomes), so a reader does not go looking for a missing model.
2. **Only `withdrawn` is added to the status enum.** `cancelled` waits for SCRUM-43, where `approved` first exists. Following [ADR-0035](0035-venue-booking-requests.md) §3, a value is added when it has code: `cancelled` now would be a value nothing can produce and no test can reach. Migration `0023` also adds the two history kinds below.
3. **"Active" is defined by exclusion.** `RETIRED_REQUEST_STATUSES` holds `withdrawn` today, and `list_active_arrangements` and `count_active_arrangements` return everything else. SCRUM-43 adds `cancelled` and `rejected` to the set; `on_hold` stays active when SCRUM-43 and SCRUM-75 add it, which is what SCRUM-75's "more than one active venue arrangement" needs. The consumers are **SCRUM-75** (the multi-venue test), **SCRUM-49** and **SCRUM-97**.
4. **Withdraw is `pending` to `withdrawn` only.** Any other status is a `409` naming the current status, as `raise_booking_request` does for a wrong-status event. Only the event's assigned coordinator may; another coordinator gets `404` ([ADR-0035](0035-venue-booking-requests.md) §6). An arrangement id that belongs to another event is a `404` too. Withdrawing one arrangement leaves the event's others untouched.
5. **Arrangements keep a status instead of being deleted,** unlike equipment lines, which `remove_equipment_line` hard-deletes. SCRUM-75 ignores withdrawn and cancelled arrangements, and SCRUM-94 expects an expired hold to stay visible in history; both require the retired row to exist.
6. **`cancel-all` keeps AC6's own word although today it only withdraws.** It retires every active arrangement in one call, is a no-op returning an empty list when there are none, and skips arrangements already withdrawn. The route and service names mean SCRUM-43 widens what it retires without renaming a published endpoint.
7. **Neither the venue nor the period changes on an existing arrangement.** Together they are the slot Venue Staff were asked about, so moving either is a new ask: withdraw and raise another. Withdrawing frees `uq_venue_booking_requests_pending`, which covers `pending` rows only ([ADR-0035](0035-venue-booking-requests.md) §2), so the same slot can be raised again; a test pins that. It also keeps the change path free of period arithmetic and of the opening-hours check.
8. **A change is partial and only on a pending arrangement.** `purpose`, `expected_occupancy`, `required_layout` and `justification` may change, shaped like `update_equipment_line`: only the fields sent change. A decided arrangement is a `409`, because changing it would quietly void Venue Staff's decision. Suitability is re-checked against the **merged** values (what is sent, else what is stored) with the existing `_venue_is_suitable`, and a justification is required when the venue no longer suits them, as in [ADR-0035](0035-venue-booking-requests.md) §7. That check runs before anything is written, so a refused change leaves the row untouched.
9. **A change clears the layout by sending `required_layout` as `null`.** `ChangeArrangementSchema` carries `allow_none=True` for that field only, mirroring `update_equipment_line`'s documented behaviour ("only the fields in `payload` change; `notes` is cleared only when sent as `null`"). The venue, the period and every other field keep "absent means leave alone".
10. **History is an audit trail the team asked for, not an AC,** for the same reason as [ADR-0035](0035-venue-booking-requests.md) §8. `venue_arrangement_changed` (details: the arrangement id, venue id, and each changed field with its previous and new value) and `venue_arrangement_withdrawn` (the arrangement id and venue id) are written through `record_event_history` in the same commit as the change they record, so there is never a change without its entry. `actor_id` is the coordinator. A change that alters nothing writes no entry.
11. **Cancel-all commits once.** It loops the same helper that single withdrawal uses and commits at the end, so a refusal partway through would commit nothing.
12. **Deferred acceptance criteria, each with its owner.**
    - AC6's "cancelling": the `cancelled` status and the `approved` to `cancelled` transition, with `venue_arrangement_cancelled` history: **SCRUM-43**, where `approved` first exists.
    - AC4's conflict detection between arrangements for the same venue: **SCRUM-44**. Different venues never conflict, because `_booking_holds_venue` filters on `venue_id`.
    - `on_hold` in AC5 and AC7: **SCRUM-43** and **SCRUM-75**.
    - Releasing a confirmed `Booking` when its arrangement is cancelled: **SCRUM-43**; no `Booking` row is written by any code path yet.
    - Notifying anyone about a change, withdrawal or cancellation: **SCRUM-50**.
13. **Defaults to review (not agreed with the team).** The ACs do not settle these, so the code accepts them rather than guessing a rule:
    - **Withdraw versus cancel is split by the arrangement's status,** with cancel left to SCRUM-43. The ACs define neither word, and this is the reading under which both are needed.
    - **AC6's "cancelling" is deferred rather than built against an unreachable status.** The alternative was to add `cancelled` now and `pragma`-exclude code no test can reach.
    - **A decided arrangement cannot be changed;** the ACs do not say when changing stops being allowed.
    - **Neither the venue nor the period can be changed** on an existing arrangement. Withdraw and raise another.
    - **`cancel-all` keeps AC6's word** although today it only withdraws, so SCRUM-43 need not rename a published route.
    - **No notifications.** AC6 asks for none and SCRUM-50 owns them, but a coordinator withdrawing an arrangement Venue Staff have been told about arguably ought to tell them.
    - **The downgrade deletes withdrawn arrangements rather than reverting them,** so it is lossy.
    - **`required_layout` can be cleared with `null`; nothing else can be cleared.**
    - **A reason is not required to change an arrangement,** unlike the justification rule. Arrangements carry no note field; the only requirement is a justification when the changed arrangement no longer suits its venue, and otherwise none is asked for.
    - **A change that alters nothing is accepted silently** and writes no history entry.

## Consequences
- AC6's core promise holds and is tested: withdrawing or changing one of three arrangements leaves the other two as they were.
- SCRUM-75, SCRUM-49 and SCRUM-97 can ask for an event's active arrangements through the venue service, without reaching into the model.
- **The migration's downgrade is lossy.** `downgrade()` deletes rows whose status is `withdrawn` (`DELETE FROM venue_booking_requests WHERE status = 'withdrawn'`) instead of reverting them to `pending`. Reverting would resurrect retired work as live Pending requests, and could violate `uq_venue_booking_requests_pending` when a withdrawn and a pending row share an event, venue and period, which this story makes reachable because withdrawing frees that index. Migration `0022` set the precedent of deleting rows whose enum value disappears.
- **The downgrade drops and re-creates the partial unique index around the enum rebuild.** Without that, `ALTER TYPE ... RENAME TO ..._old` and the column re-cast make Postgres re-create the index with its `WHERE status = 'pending'` predicate deparsed against the renamed type, and it fails with `operator does not exist: booking_request_status = booking_request_status_old`. This was found by replaying the migration on a real Postgres cluster, which the unit suite and SQLite do not do. Anyone adding a value to this enum later hits the same trap.
- Event history views must tolerate the new `venue_arrangement_changed` and `venue_arrangement_withdrawn` kinds.
- Venue Staff are not told when an arrangement they were notified about is withdrawn or changed, until SCRUM-50.
- A coordinator who typed the wrong venue or period must withdraw and raise another; there is no move.
- The shared test helpers `SECOND_PERIOD`, `two_venues` and `two_arrangements` live in `backend/tests/venue/conftest.py`, extracted on their second real use.

## Revisit when
- SCRUM-43 adds `approved`, `rejected`, `on_hold` and `cancelled`: extend `RETIRED_REQUEST_STATUSES`, widen `cancel-all`, add `<id>/cancel` and `venue_arrangement_cancelled`. Note that anyone adding a value to `booking_request_status` must keep the downgrade's index drop and re-create.
- **SCRUM-43 makes the commit-once rollback reachable.** `cancel_all_arrangements` commits once, so a refusal partway through would commit nothing, but `list_active_arrangements` returns only `pending` rows today, so that refusal cannot fire inside the loop. The guard itself is covered through `withdraw_arrangement`; the rollback path becomes reachable, and needs a test, when `approved` exists.
- SCRUM-50 adds notifications for a change, withdrawal or cancellation.
- The team decides whether a change should be able to move the period or the venue, rather than withdraw and raise another.
- The team decides any of the defaults in decision 13.
