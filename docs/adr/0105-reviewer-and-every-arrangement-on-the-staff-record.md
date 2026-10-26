# ADR-0105: The staff record shows each line's reviewer and every arrangement; the coordinator's page lists every arrangement

- **Status:** Accepted. Who sees the reviewer is SCRUM-48 AC5 (25 Oct), every arrangement on the staff record SCRUM-24 AC9 (25 Oct), and the arrangements on the event page itself with each hold's expiry SCRUM-93 AC5 and the Product Owner's decision of 25 Oct. Using one line shape and one arrangement shape for every record, and giving the coordinator's record only the arrangements, are defaults to review
- **Date:** 2026-10-26
- **Stories:** SCRUM-48 AC5; SCRUM-24 AC9; SCRUM-84 AC2; SCRUM-85 AC2; SCRUM-93 AC5
- **Supersedes:** [ADR-0095](0095-read-only-event-record-for-internal-staff.md) decision 4 (only the arrangements that still count) and the line and arrangement shapes of its decision 3
- **Builds on:** [ADR-0104](0104-organiser-sees-everything-on-the-record.md) (the record's line and arrangement shapes)

## Context
SCRUM-48 AC5 (25 Oct): "The outcome, the note, the quantity provided and the reviewing staff member are visible on the event record to the assigned Event Coordinator, the Event Coordinator Lead, Venue Staff, Technical Support Staff, the Safety Officer and the Event Organiser (SCRUM-24). Event Coordinators not assigned to the event cannot see them." The staff record (ADR-0095) reused the Safety Officer's equipment line, which has no reviewer, so the Lead, Venue Staff and the Safety Officer never saw one; the review of #137 noted it.

SCRUM-24 AC9 (25 Oct) lists "every venue arrangement with its status (including Withdrawn, Cancelled and Expired arrangements, SCRUM-93)" on the staff record, and "the current safety outcome (earlier outcomes are in the history, SCRUM-98)". ADR-0095 decision 4 left withdrawn and released ones out.

SCRUM-84 AC2 and SCRUM-85 AC2 (25 Oct) ask the team to check that a coordinator not assigned to the event can't see the preparation details.

SCRUM-93 AC5 (25 Oct): all of an event's arrangements and their statuses are listed "on the event record, on the event page itself", and an On Hold one shows its hold expiry there, or that it has expired.

## Decision
1. **The staff record's lines are the record's own shape,** `EquipmentLineOnRecord` (`RecordEquipmentLineSchema`), which the organiser's record already sends (ADR-0104): the type by name, quantity, technical notes, status, quantity provided, shortfall, outcome note, and who reviewed it when, by name. The Safety Officer's own list keeps `SafetyReviewEquipment`. Every reader of the staff record (the Lead, Venue Staff, Technical Support, the Safety Officer) sees the reviewer; the assigned coordinator already reads it on the Equipment page (`GET …/equipment`).
2. **The staff record lists every arrangement, in full,** through the same `list_every_arrangement_for_record` and `RecordVenueArrangementSchema` as the organiser's record: any status, earliest first, with where the venue is and what it offers (capacity, facilities, accessibility features), what was asked for, Venue Staff's reason, the hold's expiry and each flag with its reason. The active-only `list_arrangements_for_record`, `StaffVenueArrangementSchema` and the frontend's `StaffVenueArrangement` are gone, so every record draws one arrangement shape. The safety outcome is still only the current check's (ADR-0095 decision 5).
3. **An unassigned coordinator sees no preparation anywhere.** Every read a coordinator can make that carries preparation (their venue requests, the reservations, their own record and the history) answers an event not assigned to them `404` "Event request not found.", and the staff record refuses every coordinator by role (`403`). This needed no code change; `test_preparation_visibility.py` pins it.
4. **The coordinator's record lists every arrangement** (`CoordinatorEventRecord.venue_arrangements`, the same full shape), so the event page shows a "Venue arrangements" section for the coordinator, with each status, hold expiry ("Hold expires …" / "Hold expired …") and flag. The planning notes, reservations and safety check stay off the coordinator's record: they work on those from their own pages. *Default to review.* SCRUM-93 is Gyaltsen's story; this is its own commit so it can be reviewed or moved on its own.
5. **The mock backend does the same** (CONVENTIONS §14): the staff record mock sends each line in full and every arrangement from the booking mock (the Safety Officer's mock's venues and lines are filled out to the same shape, with no reviewer, since that mock keeps none), and the record mock gives the coordinator the arrangements.

## Consequences
- SCRUM-48 AC5 is met for every role it names; SCRUM-24 AC9's arrangement list and SCRUM-93 AC5's event-page list are met.
- The organiser's and the staff record now build the same four sections from the same readers; only the lookup and the dataclass differ, which a later refactor could fold into one.
- Internal staff see more of each arrangement than before (the location, what the venue offers, what was asked for, Venue Staff's reason, any flag), and the shortfall on each line the organiser's page draws.

## Revisit when
- The Product Owner wants retired arrangements kept off any record, or more of the safety history on it.
- The coordinator's record should carry the rest of the record too (the planning notes are on their edit form today).
