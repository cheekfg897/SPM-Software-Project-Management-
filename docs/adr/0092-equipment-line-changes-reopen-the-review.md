# ADR-0092: Equipment lines change until the event is Confirmed, and a change reopens the line for Technical Support

- **Status:** Accepted; the edit window until Confirmed (awaiting clarification and Safety Review included), reopening a changed line by clearing its outcome, releasing a removed line's reservations and closing its request, and telling Technical Support are SCRUM-37 AC2 and AC4 and SCRUM-38 AC5; counting a type change like a quantity change is decided (the Product Owner's answers of 25 Oct, answer 5), as is a lower quantity keeping the full reservation until Technical Support act (answer 7); releasing a reservation when a line moves to another type, the history wording and the one notice per change are defaults to review; a line change in Safety Review follows [ADR-0107](0107-tell-the-safety-officer-of-changes-in-safety-review.md)
- **Date:** 2026-10-19
- **Stories:** SCRUM-37 AC2, AC4 (reworked); SCRUM-38 AC4, AC5
- **Extends:** [ADR-0019](0019-event-equipment-lines.md): equipment lines; [ADR-0025](0025-event-edits-significant-changes-and-history.md): significant changes and the history; [ADR-0040](0040-equipment-review-outcome.md): the outcome on a line; [ADR-0087](0087-withdrawn-safety-approval-returns-the-event-to-approved.md): the withdrawn safety approval
- **Supersedes:** [ADR-0028](0028-review-and-decide.md)'s `EQUIPMENT_EDITABLE_STATUSES` and its message; [ADR-0029](0029-clarification-requests.md) decision 32-4 (equipment locked while awaiting clarification); [ADR-0040](0040-equipment-review-outcome.md)'s refusal of a quantity below the outcome

## Context
SCRUM-37 was reworked after it was Done. Its AC2 and AC4 now say:

* **AC2:** a line can be added, edited or removed at any time before the event is Confirmed. Once it is Confirmed, lines are locked and any change goes through a change request (SCRUM-56, SCRUM-57).
* **AC4:** adding a line, changing its quantity or removing it is a significant change (SCRUM-33). A new or changed line has no current outcome and awaits Technical Support's review; if it had an outcome, that outcome stays in the event history. A removed line releases its reservation and its request is closed. Technical Support Staff are notified (SCRUM-60), and the event cannot enter Safety Review or be confirmed until every remaining line has a current outcome. If the event has passed its safety check, the approval is withdrawn.

The "Edit window clarification" says the customer wants Technical Support to re-check suitability after a change, and that reopening the line makes that concrete, "so a recorded outcome can never be left describing a quantity that has since changed". SCRUM-38 gained AC5: a request returns to Technical Support's list when its line is added or changed and has no current outcome again.

The safety part of AC4 is already built ([ADR-0019](0019-event-equipment-lines.md) decision 11, ADR-0087). Before this ADR:

* lines could change only while the event was submitted, under review or approved;
* a line change wasn't written to the event's history (ADR-0025 decision 3);
* a recorded outcome stayed on a changed line, and a quantity below it was refused (ADR-0040);
* removing a line left its reservation in place and told nobody.

## Decision
1. **Lines change until the event is Confirmed (AC2).** `EQUIPMENT_EDITABLE_STATUSES` is submitted, under review, awaiting clarification, approved and Safety Review. Confirmed, completed, cancelled and rejected stay locked, with `409 equipment_not_editable` and the message "Equipment can only be changed before the event is confirmed, and not once it is rejected or cancelled." A draft is still a `404` to staff (ADR-0024).
   - **Awaiting clarification and Safety Review are included,** as SCRUM-37 AC2 says ("at any time before the event is Confirmed"). SCRUM-33's status clarification of 19 Oct lists the same statuses for direct edits (Submitted, Under Review, Awaiting Clarification, Approved, Safety Review). ADR-0029 had locked equipment while awaiting clarification because the request is the organiser's to amend; the organiser never edits equipment lines, so the two don't clash.
   - **In Safety Review,** *superseded by [ADR-0107](0107-tell-the-safety-officer-of-changes-in-safety-review.md) (SCRUM-33 AC9): every Safety Officer is told of a line added, changed or removed, and a line added or changed, having no outcome, sends the event back to Approved.* Before that, a change before the Safety Officer's outcome left the event in Safety Review: confirmation then waited for the new outcome (decision 5). A change after the Safety Officer approved withdraws the approval and sends the event back to Approved (ADR-0087), so it needs a new check.
2. **What counts as a change** is unchanged from ADR-0019 decision 11. **Decided by the Product Owner (25 Oct, answer 5):** a new type counts like a new quantity and reopens the line for review, the "safe reading" built while the question was open (the Product Owner's Sprint 3 open-decisions list (19 Oct), §1.7): adding a line, removing one, or a new `quantity` or `equipment_type_id`. New technical notes alone, or the values the line already has, are not a change and touch nothing below.
3. **A change is written to the event's history as a significant change (AC4).** It reuses SCRUM-33's `field_changed` entry, so no new history kind and no migration. `details` is `{"field": "equipment_line", "previous_value", "new_value", "significant": true}`, and the actor is the coordinator.
   - Each value is the line as text, e.g. `"Projector, quantity 2"`. It is `null` before an added line and after a removed one.
   - The type's name is copied in when the change is made, like an outcome's entry (ADR-0040), so the entry reads the same if the catalogue is renamed.
   - The web app already shows `field_changed` entries as "Equipment line changed", with Before and After.
   - The organiser sees these entries too, as they see other significant changes: they already see each line's type and quantity (AC5). Technical notes are never in them.
   - **Default to review:** the text values. Structured values (`equipment_type_id`, `quantity`) would need the web app to learn a new shape.
   - This supersedes ADR-0025 decision 3's "a line's own edit isn't written to the event's history".
4. **A new or changed line has no current outcome (AC4).** Its `status` goes back to `requested`, and `provided_quantity`, `outcome_note`, `reviewed_by` and `reviewed_at` are cleared, in the line's own commit.
   - The outcome stays on record in its `equipment_outcome_recorded` history entry (SCRUM-48), which is never touched.
   - A lower quantity is no longer refused for being below what Technical Support said they would provide: the outcome it would contradict is gone. This supersedes ADR-0040's `400` on `quantity`, and ends the "stale outcome" gap ADR-0040 left open.
5. **The gates need nothing new.** `lines_without_outcome` reads `provided_quantity IS NULL`, so a reopened line holds back both `submit_for_safety_review` (SCRUM-97) and `confirm_event_request` (SCRUM-49), naming the line under `equipment`.
6. **A removed line releases its reservations, and its request is closed (AC4).**
   - The new `equipment.services.release_reservations(event_id, equipment_type_id)` deletes every `EquipmentReservation` of that type for the event, in the line's own commit, so the units are free again for the period. The events module calls it through the equipment module's services, never its models.
   - Reservations hold no line id, only the event and type (ADR-0040 decision 1), and one line per type is the rule (ADR-0019 decision 4), so "the line's reservation" is the event's reservations of its type.
   - The line itself is still deleted (ADR-0019), which closes its request: it can't be on Technical Support's list (SCRUM-38 AC4). The `equipment_reserved` history entries stay.
   - **Default to review:** a line moved to another equipment type releases the old type's reservations the same way, since the event no longer asks for that type.
   - A new quantity keeps the reservations: Technical Support re-review the line and decide. **Decided by the Product Owner (25 Oct, answer 7):** a lower quantity keeps the full reservation until Technical Support act by hand; nothing shrinks it automatically.
     - **Not built:** Technical Support have no way to act by hand yet. The equipment routes reserve, list reservations and record their preparation, but nothing releases or shrinks one, so today the extra units stay reserved for the event's period unless the line is removed, moves to another type or the event is rejected. A ticket to open: let Technical Support release part or all of a reservation.
7. **Technical Support Staff are told (AC4, SCRUM-60).** After the line's own commit, each one gets a `significant_change` notice for a changed or removed line ("An event you have arrangements for has changed significantly. Please check they still fit.", ADR-0025 decision 13).
   - An added line keeps its one `equipment_requested` notice (AC6) rather than a second one.
   - A notice that fails to save is logged and doesn't undo the change (ADR-0015). Nobody else is told.
   - **Default to review:** one notice per change, with no detail naming the line; the history says which line.
8. **A reopened line is back on Technical Support's list (SCRUM-38 AC5)** with no change to the list itself, which shows every line still `requested` (ADR-0022).
9. **Everything rides in one commit.** The history entries, the cleared outcome, the released reservations and any safety withdrawal are saved with the line or not at all. A change refused as a duplicate type (`409`) leaves the outcome, the reservations and the history as they were.

## Questions for the Product Owner
1. ~~Does changing a line's equipment type reopen it like a quantity change? We built the "safe reading", yes, which also withdraws a safety approval and releases the old type's reservations.~~ Answered on 25 Oct (answer 5): yes, as built.
2. ~~Does a lower quantity shrink the reservation?~~ Answered on 25 Oct (answer 7): no; the full reservation stays until Technical Support act by hand. Nothing shrinks it, as built, but they can't act by hand yet (decision 6).

## Consequences
- The frontend's mock (`frontend/src/mocks/handlers/equipmentLines.ts`) accepts the same statuses, answers with the new message, clears a changed line's outcome and no longer refuses a lower quantity. Its integration tests for the line routes are still `it.todo`, waiting for an assigned event to test against. The mock keeps one list of reservations shared by every event, so it does not release any when a line is removed; that waits for the mock to track reservations per event.
- A coordinator can reopen a line Technical Support has finished with, at any time before confirmation. Each change costs Technical Support a fresh review, which is what the customer asked for.
- A line moved to another type loses its reservations at once. If the coordinator moves it back, Technical Support reserve again.

## Revisit when
- ~~The Product Owner answers the question above: if a type change does not count, `_changes_the_equipment` stops counting `equipment_type_id`.~~ Answered on 25 Oct: a type change counts.
- Change requests for Confirmed events (SCRUM-56, SCRUM-57) are built: they decide how a Confirmed event's lines change.
- Technical Support want a lower quantity to shrink a reservation, rather than keep it until they act. The Product Owner said no on 25 Oct (answer 7), so only a new request reopens this.
- A route lets Technical Support release part or all of a reservation by hand (decision 6): the reading of answer 7 is then complete.
- The customer says the coordinator shouldn't change equipment while the organiser is answering a clarification.
