# ADR-0046: Technical Support take units of an equipment type out of service; reservations left short are flagged, never released

- **Status:** Accepted; the decisions below are defaults to review with the team; AC5, deferred in decision 9, is built in decision 10
- **Date:** 2026-10-16
- **Story:** SCRUM-47 Take damaged equipment out of circulation
- **Extends:** [ADR-0037](0037-equipment-availability-and-reservation.md): the `equipment_out_of_service` seam and the lock; [ADR-0015](0015-in-app-notifications.md): notifications after the commit

## Context
SCRUM-47's ACs: an equipment item's operational status can be set to Available, Damaged or Under Maintenance (AC1); items that are not Available are excluded from availability (AC2); reservations depending on the affected items are flagged and the responsible coordinator is notified (AC3); the change records the user and the timestamp (AC4); a flagged reservation on an event that already passed its Operational Safety Check forces a new check (AC5).

The catalogue has no per-item table (ADR-0037), so "an item" can only mean a number of units of a type. The ACs leave open how a status is set, which reservations "depend on" an item, who is told and how, and what AC5 does before a safety check exists.

## Decision
1. **A status change is a set of units, not an item.** `POST /api/equipment/types/<id>/out-of-service` takes `quantity` and `reason` (`damaged` or `under_maintenance`) and records one `equipment_out_of_service` row, which counts against availability until it is returned (AC1, AC2). `POST /api/equipment/out-of-service/<id>/return` sets `resolved_at` and puts those units back ("Available"). `GET /api/equipment/types/<id>/out-of-service` lists the entries still out, so the ids to return can be found. Technical Support Staff only: every other role is `403`.
2. **Units come back in the batches they went out.** Returning resolves the whole entry; a partial return is not supported. To return some of an entry's units, Technical Support record the rest again. Returning an entry that is already back is `409`.
3. **No more than are in service can be taken out:** a `quantity` above `total_quantity` less the unresolved entries is `400` on `quantity`, "Only N units are in service.".
4. **Who and when (AC4).** `recorded_by` and `recorded_at` say who took the units out and when; migration `0038_add_out_of_service_audit` adds `resolved_by` for who returned them (`resolved_at` already existed). They are shown by name, as reservations are. No event history entry is written: the entry is about an equipment type, not an event.
5. **Which reservations are "short" (AC3).** Out-of-service units belong to no period (ADR-0037), so a broken unit can't be traced to the reservation that held it. A coming reservation is flagged when the units reserved for events overlapping its period, counted as availability counts them, exceed the units in service. Every reservation in an over-committed period is flagged, not only the latest. Reservations that have already ended are left alone; reservations of other types or other, uncrowded periods are not touched. Flagging is the `needs_attention` column on `equipment_reservations` (same migration, default false) and is shown on the reservation reads. **Nothing is released or deleted.**
6. **The flag follows the numbers.** Every change re-evaluates the type's coming reservations, so returning units clears the flags that no longer apply.
7. **The coordinator is told once per event, when a reservation is newly flagged** (AC3). The events module sends it after the commit (ADR-0015) to the event's assigned coordinator, with the existing `significant_change` kind ("An event you have arrangements for has changed significantly. Please check they still fit.") and a `detail` saying equipment reserved for the event is no longer all available. A reservation that was already flagged does not tell them again; returning units tells nobody. An event with no coordinator is logged, as for other equipment notices. A kind of its own was not added, so there is no enum migration; SCRUM-50 does not list this notice.
8. **The type is locked** with `_locked_equipment_type` before the change, as ADR-0037 requires, so a reservation made at the same moment is either counted before the change or flagged by it.
9. **AC5 is deferred.** The Operational Safety Check does not exist yet (SCRUM-97, SCRUM-98, as in [ADR-0040](0040-equipment-review-outcome.md)). `needs_attention` is the seam: those stories decide whether a flagged reservation on a checked event forces a new check. *(Built once they landed: decision 10.)*
10. **AC5: a newly flagged reservation withdraws the safety approval.** For each event decision 7 would tell (a reservation of it newly flagged by this change), `mark_out_of_service` calls `events.services.withdraw_safety_approval` in the change's own commit. If the Safety Officer has approved the event, that writes a `safety_approval_withdrawn` history entry with the Technical Support user as actor and `details = {"equipment_type_id", "equipment_type_name", "units_out_of_service"}`, and an event in Safety Review or Confirmed goes back to Approved ([ADR-0087](0087-withdrawn-safety-approval-returns-the-event-to-approved.md)). The entry is internal-only; the coordinator gets decision 7's notice and nothing more. **Default to review:** a reservation that was already flagged when the Safety Officer approved the event withdraws nothing when more units go out, just as it doesn't notify again, since the officer approved it with the flag on. Returning units never restores an approval.

## Consequences
- Availability stays one formula; marking and returning units only add and resolve rows (ADR-0037).
- A coordinator may see a flag on a reservation that was not the one a broken unit was held for, because units are not tied to reservations.
- Because `significant_change` says the event "has changed", the notice reads slightly off; the `detail` carries the real reason.
- Downgrading migration 0038 drops `resolved_by` and `needs_attention`, losing who returned units and which reservations were flagged.

## Tickets to open
- Frontend: show `needs_attention` on the reservation list, a screen for Technical Support to mark and return units, and the matching handlers in `frontend/src/mocks/handlers/equipment.ts` and `frontend/src/integration/` (this change is backend only).
- Decide whether the coordinator needs a dedicated notification kind (a new enum value) rather than `significant_change`, together with SCRUM-50.
- Decide whether partial returns and a note on why units are out are wanted.

## Revisit when
- Per-item tracking or period-bound maintenance is wanted (ADR-0037, "Period and items").
- The team decides whether a reservation flagged before the approval should withdraw it when it gets shorter (decision 10).
