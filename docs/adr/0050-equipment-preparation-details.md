# ADR-0050: Technical Support record a preparation status and notes on an equipment reservation

- **Status:** Accepted (defaults to review); decision 7 is extended by [ADR-0095](0095-read-only-event-record-for-internal-staff.md), whose read-only record shows other internal users the preparation details; decision 6's internal-only history entry superseded by [ADR-0104](0104-organiser-sees-everything-on-the-record.md): the organiser reads it, and sees the preparation on their record
- **Date:** 2026-10-17
- **Stories:** SCRUM-85 Update equipment preparation details

## Context
SCRUM-85 lets a Technical Support member record "preparation notes and a preparation status against an equipment reservation they are responsible for" (AC1), visible to the assigned coordinator and other internal users (AC2), changing nothing else of the event (AC3), with the user and time of each update (AC4), and only once the Safety Officer has approved the event (AC5, ADR-0047 decision 18). It mirrors SCRUM-84 (ADR-0049) for venues. The ACs do not say what the statuses are, who counts as "responsible", or how an update treats the notes already there.

## Decision
1. **The reservation is the `equipment_reservations` row** (SCRUM-46): the units held for an event's period. The details live on it: `preparation_status` and `preparation_notes`.
2. **Three statuses, as for venues: `not_started` (every reservation begins here), `in_progress` and `ready`.** The enum is the equipment module's own, with the same values as the venue module's: a module never imports another module's models. The notes rules (optional, never blank, trimmed, at most 1,000 characters) and the gate's message are the venue module's too, so both modules take them from `app/common/preparation.py` (CONVENTIONS §7: code two modules use).
3. **"Responsible for" is any Technical Support member.** Nothing assigns a reservation, or an equipment type, to a staff member: the reserver is whoever reserved it, and the reservation, availability and outcome routes are open to all Technical Support (ADR-0037, ADR-0040). The product owner removed "responsible for" from the venue stories for the same reason (ADR-0035 decision 1); SCRUM-85 still carries it. Other roles get `403` from the role check. **Open question for the product owner:** if responsibility should mean the reserver, or a new assignment, a check is added in `update_preparation_details`.
4. **`PUT /api/equipment/reservations/<id>/preparation`, body `status` (required) and `notes` (optional).** Each update states the whole picture: notes left out are cleared. A field other than these two is a `400`, which is how AC3 holds: the route has no way to change the quantity, type or period. Notes that are sent must not be blank, are trimmed, and are at most 1000 characters (the column is `Text`, so this is an API rule).
5. **The gate is `events.services.has_safety_approval`** (AC5). Without it the update is `409` with `PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE` and nothing is saved. There is no reservation status to check, unlike a venue request.
6. **Each update is an `equipment_preparation_updated` history entry** (AC4): the Technical Support user as actor, the time, and `details` of `reservation_id`, `equipment_type_id`, `equipment_type_name`, `status` and `notes`, saved in the same commit as the details. It is internal-only, like the reservation itself (ADR-0037), so the organiser does not see it.
7. **Who can read it** (AC2). The assigned coordinator reads `preparation_status` and `preparation_notes` on the event's reservations, through the route that already lists them (SCRUM-46 AC4). Every internal role reads the history entry through the event history route. There is no separate read route for other internal users.
8. **Migration `0034_add_equipment_preparation`** adds the two columns (existing rows start `not_started`), the `equipment_preparation_status` enum and the history kind, outside the transaction. Downgrade is lossy: the entries of the new kind are deleted.

**Defaults to review (not agreed with the team):** decisions 2 (the status names), 3 (any Technical Support member), 4 (an update replaces the notes) and 7 (no read route beyond the reservations list and the history).

## Still owed
- **Frontend:** a Technical Support form for the details, and the coordinator's view of them.

## Revisit when
- The team settles decisions 2, 3, 4 or 7.
