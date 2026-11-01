# ADR-0128: Two change request defaults waiting for the Product Owner

- **Status:** Proposed; both are defaults pending the Product Owner
- **Date:** 2026-11-01
- **Story:** SCRUM-57 Review and decide a change request
- **Extends:** [ADR-0127](0127-decide-a-change-request.md)

## Context
Two questions SCRUM-57 raises aren't settled by its criteria or comments, and we built a default for each so the story can be reviewed.

The first is what an approved change to the equipment requirements does. The Organiser's change request carries `equipment_requirements`, the event's free-text field. Since SCRUM-37 the coordinator also keeps equipment lines (a type and a quantity) that Technical Support review and reserve against. The criteria say approving applies the change, but not whether it touches those lines.

The second is an overlap with SCRUM-62. SCRUM-57 AC7 tells registered Attendees when an approved change moves the event's date or time. SCRUM-62 AC2 (in review, PR #166) also tells Attendees of changes to an event they registered for. Building it in both places would send two notices for one change.

## Decision
1. **An approved change to the equipment requirements edits the free text only.** The equipment lines stay as the coordinator left them, and the coordinator turns the new text into lines, as after a direct edit. Technical Support are still told of the change, as after a direct edit, and a date or time change marks the reservations for reassessment (ADR-0127 decision 7).
2. **SCRUM-57 sends the date-and-time notice to Attendees** (`event_rescheduled`, ADR-0127 decision 9), since AC7 is its own. SCRUM-62 should not add a second one for an approved change request. If the Product Owner wants SCRUM-62's notice to cover it instead, this one is removed.

## Consequences
- After an approval the free text and the lines can disagree until the coordinator updates the lines.
- PR #166 adds a private `_registered_attendee_ids` to the registration module. This branch adds a public `list_registered_attendee_ids`; whichever merges second should use the other's.

## Revisit when
- The Product Owner answers either question.
