# ADR-0019: Equipment lines are recorded per event by Event Coordinators while the request awaits review

- **Status:** Accepted; a draft is `404` to staff, not `409`, superseded by [ADR-0024](0024-draft-event-requests.md); decision 3 superseded by [ADR-0028](0028-review-and-decide.md): equipment may also change while `approved`, and the refusal is `409 equipment_not_editable`; decision 11 adds the safety approval part of the reworked AC4 (Week 7); the rest of that AC is not built yet
- **Date:** 2026-09-25
- **Story:** SCRUM-37 Record what equipment an event needs

## Context
SCRUM-37 lets an Event Coordinator record the equipment an event needs so Technical Support Staff know what to arrange. Its five ACs say: add one or more lines, each with an equipment type, a quantity and technical notes (AC1); edit or remove a line "while the request is still awaiting review" (AC2); refuse a quantity of zero or less (AC3); show "the equipment request and its current state" on the event record (AC4); and notify Technical Support Staff "when equipment is requested" (AC5). The story's Roles field names the Event Organiser, the Event Coordinator and Technical Support Staff.

Several things are left open:
1. **Who may record and who may read.** The story is written for coordinators, but there is no event view for internal staff yet (ADR-0012, ADR-0017), and coordinators aren't assigned to requests until SCRUM-30.
2. **What "awaiting review" means** among the seven statuses of ADR-0012.
3. **Whether an event may have two lines for the same equipment type.**
4. **What "its current state" is.** Nothing reserves equipment yet; SCRUM-46 will.
5. **Whom to notify, and how often.** Postgres enum values can be added but never removed (ADR-0012), so a new notification kind is a one-way step.
6. **The shape later stories need.** SCRUM-38 lists every equipment request "not yet resolved" per event with its types and quantities; SCRUM-46 reserves "up to the available quantity of an equipment type for the event's period", linked to the event.
7. **By when.** The story says Technical Support must know what to arrange "and by when", but no AC gives a line a date.

## Decision
1. **Coordinators write, coordinators and Technical Support read, the organiser sees their own.** Adding, editing and removing lines is `event_coordinator` only. `GET /api/events/requests/<reference>/equipment` is open to `event_coordinator` and `technical_support_staff`. Decision 2 narrows which coordinator. The Event Organiser sees the lines embedded in their own `GET /api/events/requests/<reference>`.
2. **Only the event's assigned coordinator (SCRUM-30, ADR-0018).** A coordinator adds, edits, removes and lists lines only on a request assigned to them; the services take the caller's user id, as the organiser's do. Another coordinator's request, or an unassigned one, is a `404` "Event request not found.", the same answer as an unknown reference and the organiser's "not yours" (ADR-0012): a `403` would confirm the reference exists. Technical Support Staff list the lines of any request. The reference ignores case and surrounding spaces (ADR-0004).
3. **"Awaiting review" is `submitted` or `under_review`.** In `draft`, `confirmed`, `completed`, `cancelled` or `rejected`, adding, editing and removing are all refused with `409 request_not_awaiting_review`. *(Superseded by [ADR-0028](0028-review-and-decide.md): the set is now `EQUIPMENT_EDITABLE_STATUSES = {submitted, under_review, approved}` and the refusal is `409 equipment_not_editable`.)*
4. **One line per equipment type per event,** enforced by a unique constraint. A second line for the same type is a `409` telling the caller to edit the existing line.
5. **"Current state" is a per-line `status`.** Only `requested` exists for now (the Postgres enum `event_equipment_line_status`); SCRUM-46 adds `reserved`.
6. **Every Technical Support Staff member is notified once per added line** (notification kind `equipment_requested`). The notification is raised after the line's own commit, in a second commit that may fail without failing the add (ADR-0015). Editing or removing a line notifies nobody.
7. **Technical notes are optional free text,** trimmed, with blank notes stored as `NULL` and no length cap.
8. **Editing is partial.** `PATCH` may change `equipment_type_id`, `quantity` and `notes`; only the fields sent change, and `notes` is cleared only when sent as `null`. An empty body changes nothing and returns `200`.
9. **"By when" is the event's own date and times.** `GET /api/events/requests/<reference>/equipment` returns `{"event": {...}, "equipment_lines": [...]}`, where `event` holds `reference`, `name`, `proposed_date`, `end_date`, `start_time` and `end_time`, dumped by the request's own schema so the names and formats match `GET /api/events/requests/<reference>`. `end_date` is included because an overnight event ends the day after it starts (ADR-0002). Lines have no needed-by date of their own: that would need a migration, and nothing asks for lines needed at different times.
10. **Rolling back migration 0011 deletes `equipment_requested` notifications,** because Postgres can't remove the enum value and those rows would have no kind to go back to. The same lossy rollback as migration 0006 (ADR-0012).
11. **A line change withdraws a safety approval (reworked AC4).** Adding a line, removing one, or changing its `equipment_type_id` or `quantity` to a different value withdraws the event's safety approval, if it has one, through `withdraw_safety_approval` ([ADR-0025](0025-event-edits-significant-changes-and-history.md) decision 25, [ADR-0053](0053-flag-bookings-when-a-venue-becomes-unavailable.md) decision 13). The `safety_approval_withdrawn` entry has the coordinator as actor and `details = {"equipment_line_change": "added" | "changed" | "removed", "equipment_type_id": ...}`, the line's type before the change. It is internal-only and is saved in the line's own commit, so a line refused as a duplicate leaves the approval in place. Nobody is notified ([ADR-0087](0087-withdrawn-safety-approval-returns-the-event-to-approved.md)). A line can only change while the event is `approved` or earlier, so this matters only for an Approved event that kept its approval when a flagged venue took it back from Confirmed (ADR-0053 decision 7). **Default to review:** a new equipment type counts like a new quantity, since it changes what is placed; new technical notes alone, or the values already saved, do not.

Also:
- **Lines live in the events module,** since they belong to an event request and AC4 puts them on the event record. The foreign key to `equipment_types` is database-level only, and the type is checked through `equipment.services.get_equipment_type`: an unknown type is a `400` on `equipment_type_id`.
- **Responses carry `equipment_type_id`, not the type's name,** as the catalogue already exposes ids (ADR-0014). A client reads names from the equipment catalogue.
- **Removal is a hard delete** (`204`). Nothing records who added, changed or removed a line.
- The quantity is not checked against the catalogue's `total_quantity`: this story records what is needed, and SCRUM-46 decides what can be reserved.

## Consequences
- SCRUM-38 can treat an event as unresolved while any of its lines is still `requested`, and group lines by event.
- SCRUM-46 adds `reserved` with one `ALTER TYPE ... ADD VALUE`, and should decide what an edit does to a line that is already reserved.
- A coordinator who adds five lines sends five notifications to each Technical Support Staff member.
- An unassigned request (no Event Coordinator existed when it was submitted, ADR-0018) can't have equipment recorded until someone is assigned to it. Reassignment (SCRUM-87) needs no change here: the check reads the request's current `coordinator_id`.
- Downgrading past migration 0011 loses the `equipment_requested` notifications.
- Technical Support read by when to arrange equipment from the event's date and start time; setup time (ADR-0011) is not subtracted, since the event has no venue booking yet.

## Revisit when
- The rest of the reworked AC4 is built (marking the change in the event history, clearing a changed line's outcome, releasing a removed line's reservation, telling Technical Support, and letting lines change in Safety Review): the safety withdrawal of decision 11 stays where it is.
- SCRUM-24 adds per-role event views: fold the equipment sub-resource into the event detail those roles see.
- SCRUM-46 starts: decide how reservation changes a line's status and what editing a reserved line does.
- Technical Support Staff ask for one notification per request instead of one per line.
- Technical Support need a line earlier than the event starts, or lines at different times: add a `needed_by` per line (a migration).
- A story needs an audit trail per line (who added or changed it): SCRUM-30's event history is the likely home.
