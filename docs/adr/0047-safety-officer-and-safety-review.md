# ADR-0047: The Safety Officer is an internal role, and the assigned coordinator sends a settled, approved event to Safety Review

- **Status:** Accepted (part A of SCRUM-97)
- **Date:** 2026-10-16
- **Story:** SCRUM-97 Submit an event for operational safety check

## Context
Customer change #6 adds an Operational Safety Check. SCRUM-97 adds the Safety Officer role and a Safety Review status: an event goes there once every active venue arrangement is Approved and every equipment request has an outcome from Technical Support (AC1), with equipment optional (AC2). SCRUM-98 records the Safety Officer's outcome and SCRUM-49 lets the coordinator confirm once venue, equipment and safety are all in. SCRUM-22's status list is to be reconciled with SCRUM-31 (Approved) and SCRUM-68.

The ACs say the event "moves to" Safety Review but not who or what moves it, and leave open where it sits in the lifecycle, what happens to an event with no venue, and how the role is provisioned. This ADR covers part A: the role, the status and the transition. Part B (the Safety Officer's list, the event detail they see and their notification) comes in a second pull request.

## Decision
1. **The Safety Officer is an internal staff role**, `Role.SAFETY_OFFICER = "safety_officer"`, in `INTERNAL_ROLES`. An account gets it the way every staff account does: `flask create-staff-user --role safety_officer` (ADR-0023). No new mechanism (AC7). Like every internal role, it is let into the routes open to all internal staff: the event history (internal entries included), equipment types, venue calendars, and creating client organisations (ADR-0013). The reads help part B; creating organisations goes beyond the story.
2. **`safety_review` sits between `approved` and `confirmed`.** The lifecycle is now: draft → submitted → under review (↔ awaiting clarification) → approved → **safety review** → confirmed → completed, with rejected and cancelled as exits. That is ten statuses: SCRUM-22's seven plus `approved` (SCRUM-31), `awaiting_clarification` (SCRUM-32) and `safety_review`. It is an active status, so the Lead lists it and can reassign the event (`ACTIVE_STATUSES`, ADR-0041).
3. **The assigned coordinator sends the event, with `POST /api/events/requests/<reference>/safety-review`.** The story is titled "Submit an event", and the move needs an actor for the event history. Moving it automatically would mean venue decisions (venue module) and equipment outcomes each triggering a status change in the events module. Another coordinator gets the usual "not yours" `404` and any other role `403` (ADR-0019).
4. **Only an `approved` event can be sent.** Any other status is `409 safety_review_not_allowed` with `NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE`.
5. **The gate, checked through public service functions:**
   - Venue: `venue.services.count_active_arrangements` and the new `list_unapproved_arrangements`. Withdrawn arrangements are retired and ignored; Pending and Rejected ones are active and hold the event back (AC1, Rejected venue clarification). There is no On Hold or Cancelled arrangement status yet, and the code needs no change when they arrive: anything active and not Approved holds the event back, anything retired is ignored.
   - Equipment: `lines_without_outcome` (ADR-0040). No equipment requests means nothing is outstanding, so the event passes (AC2).
   - A refusal is `409 safety_review_not_allowed` with `SAFETY_REVIEW_NOT_READY_MESSAGE` and `details` naming each gap, under `venue_arrangements` and `equipment`, so the coordinator knows what to chase.
6. **An event with no venue arranged is held back.** "Every active arrangement is Approved" is true of none, but the story's premise is that "the venue is confirmed", and a safety check without a venue has nothing to assess.
7. **The move is recorded** as a `safety_review_requested` history entry with the coordinator as actor and no details, in the same commit as the status, like `review_started` (ADR-0028). The organiser can see it, as they see the status.
8. **Migration `0029_add_safety_review`** adds `safety_officer`, `safety_review` and `safety_review_requested` outside the transaction. Downgrade is lossy: the entries are deleted, an event in Safety Review returns to `approved`, and a Safety Officer becomes an `attendee`, the one role with no staff access, before each type is rebuilt.
9. **Defaults to review (not agreed with the team):** decision 1's internal-route access (in particular creating client organisations), decision 3 (the coordinator sends it, not an automatic move), decision 6 (no venue means not ready), decision 8's downgrade of a Safety Officer to `attendee`.

## Still owed
- **SCRUM-97 part B:** the Safety Officer's list of events awaiting review, ordered by event date (AC5); the details they see (attendance, each booked venue's capacity, layout, facilities and accessibility features, the event's accessibility needs, the equipment with quantities and notes, AC6); notifying Safety Officers when an event enters Safety Review (AC4).
- **SCRUM-98:** recording Approve, Reject or Request Changes with the checklist; Reject and Request Changes return the event to planning. Also ADR-0040's deferred AC6: a revised equipment outcome after the check forces a new one.
- **SCRUM-49:** confirming the event only from `safety_review` after a safety Approve (AC3, "cannot reach Confirmed without passing through Safety Review"). Nothing moves an event to `confirmed` yet, so nothing skips Safety Review today.
- **Open:** an event in Safety Review can't be edited, nor its equipment changed, because `safety_review` is in neither `EDITABLE_STATUSES` nor `EQUIPMENT_EDITABLE_STATUSES`. SCRUM-98's Request Changes is the way back to editing. Venue arrangements are not blocked yet: the coordinator could still withdraw or change one during review. SCRUM-98 or SCRUM-49 should decide.

## Consequences
- SCRUM-98 and SCRUM-49 have the status, the role and the gate to build on.
- The frontend knows the new role and status (chip label "Safety review"); a Safety Officer lands on the staff home until part B gives them a page.

## Revisit when
- The team settles decisions 3, 6 or 8.
- On Hold (SCRUM-75) or Cancelled arrangement statuses land: check they count as active or retired as AC1 says.
