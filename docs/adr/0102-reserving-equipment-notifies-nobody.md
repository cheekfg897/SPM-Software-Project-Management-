# ADR-0102: Reserving equipment notifies nobody; the coordinator hears once, when the outcome is recorded

- **Status:** Accepted
- **Date:** 2026-10-25
- **Story:** SCRUM-46 Reserve equipment for an event (AC5)
- **Supersedes:** [ADR-0037](0037-equipment-availability-and-reservation.md) section 5 (the coordinator is notified of each reservation)
- **Extends:** [ADR-0040](0040-equipment-review-outcome.md): the outcome notification, which is now the coordinator's only notice

## Context
SCRUM-46 AC5 used to say the event's coordinator is notified when equipment is reserved. ADR-0037 section 5 built that: after the reservation's commit, `reserve_equipment` called `events.services.notify_coordinator_equipment_reserved`, which raised one `equipment_reserved` notification for every reservation.

AC5 now says: "Reserving equipment does not notify the coordinator by itself; the coordinator is notified when the outcome is recorded (SCRUM-48)." The story's notification clarification gives the reason: Technical Support usually reserve and then record the outcome, so a fulfilled request brought two notices for one piece of work. SCRUM-48 already tells the coordinator when the outcome is recorded (`equipment_outcome_recorded`, ADR-0040).

## Decision
1. **`reserve_equipment` notifies nobody.** The reservation and its `equipment_reserved` history entry are still saved in one commit (AC4); nothing follows the commit. The coordinator learns what will be provided from the outcome notification (SCRUM-48 AC3), which is unchanged.
2. **`notify_coordinator_equipment_reserved` is removed.** It had no other caller, and the events module's public surface (`events/__init__.py`) no longer lists it. With no notice there is also no "nobody assigned" warning: reserving for an event with no coordinator logs nothing.
3. **The `equipment_reserved` notification kind stays.** Dropping a value from a Postgres enum means a migration that recreates the type, and notifications already sent hold the value, so they would have to be deleted or rewritten. The kind keeps its message ("Equipment was reserved for an event.") so those older notifications still read properly; its comment in `NotificationKind` says it is no longer raised. The history kind of the same name is unaffected: the history still records every reservation.
4. **No frontend change.** The mock backend never raised a reservation notice, and no screen or contract test looks for one. A new integration test checks the real backend raises none.

## Consequences
- A coordinator whose equipment is reserved but whose outcome is never recorded hears nothing about the reservation. The reservation is still on the event's record and in its history (AC4).
- `equipment_reserved` in `notification_kind` is now a value nothing writes. A later migration that rebuilds the enum for another reason could drop it, once old notifications no longer matter.

## Revisit when
- The customer wants the coordinator told about a reservation again, for example one made without an outcome to follow.
- A migration rebuilds `notification_kind`: decide then whether to drop `equipment_reserved` and what to do with the notifications that hold it.
