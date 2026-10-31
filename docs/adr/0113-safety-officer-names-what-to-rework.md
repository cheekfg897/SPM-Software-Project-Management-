# ADR-0113: The Safety Officer names arrangements and lines to rework, which are flagged and reopened as a change would leave them

- **Status:** Accepted for what SCRUM-99's criteria settle (AC2, AC4-AC7; AC1 and AC3 were delivered by SCRUM-98); the flag being SCRUM-58's reconfirmation flag with "Flagged by the Safety Officer: <reason>" was decided by the lead before the build; decisions 2-9 were made while building and decision 10 after review: all are defaults to review
- **Date:** 2026-10-28
- **Story:** SCRUM-99 Return an event to planning when the safety check is not approved
- **Extends:** [ADR-0047](0047-safety-officer-and-safety-review.md) (Safety Review and its gate), [ADR-0094](0094-reassess-each-venue-arrangement-after-a-significant-change.md) (the reassessment flag), [ADR-0092](0092-equipment-line-changes-reopen-the-review.md) (a line reopened), [ADR-0112](0112-reconfirm-or-reject-a-flagged-booking.md) (Venue Staff settle a flag)

## Context
SCRUM-98 records Approve, Reject or Request Changes, and the last two send the event back to Approved. SCRUM-99 adds what the Safety Officer can name when not approving: venue arrangements, "flagged for re-review with the same flag as SCRUM-58", and equipment lines, "reopened as in SCRUM-37". The reason is shown as "Flagged by the Safety Officer: <reason>" beside each flagged arrangement, or on the event itself when nothing is named (AC4). A flag clears through SCRUM-59 or SCRUM-93; a line when Technical Support record its outcome (AC5). Resubmission waits for both (AC6), and Venue Staff and Technical Support are told (AC7).

## Decision
1. **The flag is the reassessment flag** (lead's decision): `requires_reconfirmation`, reason "Flagged by the Safety Officer: <reason>". It sits in Venue Staff's flagged list (SCRUM-59 AC1) and clears when they reconfirm or reject it, or when the coordinator replaces the arrangement. Nothing moved the event, so reconfirming keeps its period (SCRUM-59 AC2).
2. **The payload** of the outcome route gains `flagged_arrangement_ids` and `reopened_line_ids`, lists of positive whole numbers, each named once, both empty by default. An approval that names anything is refused on each field: "Only a rejection or a request for changes can name what to rework."
3. **What can be named:** an arrangement of this event that is Approved (in Safety Review every live arrangement is, SCRUM-97), and any of the event's lines. Every id is checked before anything changes, lines first, and each refusal names the id ("Venue arrangement 12 is not one of this event's approved arrangements.", "Equipment line 7 is not one of this event's lines.").
4. **A named line is reopened** with SCRUM-37's `_clear_outcome`: back to Requested, its outcome cleared and kept in the history, its reservations left as a quantity change leaves them. The event's history entry for the outcome keeps both lists of ids.
5. **The Safety Officer's list gives ids** to each venue (the arrangement's) and equipment line, so the web app can tick them. They were left out before as not the reader's to use (ADR-0047); naming makes them so.
6. **Who is told:** every Venue Staff user, once per flagged arrangement, and every Technical Support user, once per reopened line, with the existing `significant_change` notice and a detail naming the arrangement or line and the reason. No migration: the kind already means "something about this event needs looking at again", as for a change (ADR-0094 decision 7) or a line change (SCRUM-37).
7. **The record:** the safety outcome now says how many arrangements were flagged and lines reopened (`flagged_arrangement_count`, `reopened_line_count`), and the coordinator's own record carries the outcome too, as the staff and organiser records already did. The web app shows "Flagged by the Safety Officer: <reason>" on the event's safety check when no arrangement was flagged, because AC4 puts it beside each flagged arrangement "or on the event itself where nothing is flagged" and only arrangements are flagged (a line is reopened); otherwise it shows the plain reason, each flagged arrangement showing its own flag beside it, as every reassessment flag does. Whatever was named is counted under it, "Named to rework: 1 venue arrangement and 2 equipment lines.", leaving out a kind with none.
8. **Resubmission** needs nothing new: SCRUM-97's gate already refuses an open flag and a line without an outcome, naming each.
9. **The mock** checks the new fields as the backend does and counts what was named on the outcome. It doesn't flag the booking mock's arrangements or reopen the equipment mock's lines: each keeps its own events, as ADR-0107 decision 10 notes.
10. **Headings** (after review, 31 Oct). On the event record and the coordinator's venue requests page, a reassessment flag is headed "Flagged for re-review" (AC2's words), not "Flagged after a change to the event", since the Safety Officer's flag is not a change. Each flag's own reason still says where it came from. Venue Staff's booking page keeps SCRUM-59's "Flagged after a change" section heading until #152 settles it. A default to review.

## Consequences
- The coordinator sees what to rework on the event page, and Venue Staff and Technical Support each get it on their own lists.
- Tests: `tests/events/test_safety_officer_flags.py` (marker `scrum_99`); older safety outcome and record tests include the new fields; the safety mock's tests; `SafetyReviewPage.test.tsx`, `EventRequestPage.test.tsx`; `safetyFlags.int.test.ts` against the backend.

## Revisit when
- The team wants a notice kind of its own for a Safety Officer's flag, rather than `significant_change`.
- The record should name each reopened line beside it, as each flagged arrangement is.
