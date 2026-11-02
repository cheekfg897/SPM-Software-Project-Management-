# ADR-0129: An approved change request reassesses what a direct edit reassesses

- **Status:** Accepted; the rules in SCRUM-58's criteria and table were agreed with the Product Owner (ADR-0094's answers of 25 Oct, the rewrite of 29 Oct); decisions 3 to 6 are defaults to review
- **Date:** 2026-11-02
- **Story:** SCRUM-58 Reassess venue bookings after an approved change request
- **Extends:** [ADR-0094](0094-reassess-each-venue-arrangement-after-a-significant-change.md) (the flags and who is told), [ADR-0087](0087-withdrawn-safety-approval-returns-the-event-to-approved.md) (a withdrawn approval sends the event back), [ADR-0107](0107-tell-the-safety-officer-of-changes-in-safety-review.md) (a change in Safety Review), [ADR-0112](0112-reconfirm-or-reject-a-flagged-booking.md) (Venue Staff settle a flag), [ADR-0127](0127-decide-a-change-request.md) (deciding a change request)

## Context
SCRUM-33 AC6 and AC7 reassess the venue bookings and withdraw a safety approval when the coordinator edits an event directly (ADR-0094). A Confirmed event can't be edited directly (ADR-0101), so the case that matters most, a Confirmed event whose date moves, arrives only through a change request (SCRUM-57). ADR-0127 applied the values and handed the equipment back, and left the rest to this story. SCRUM-58 says the same checks run when the coordinator approves a change request, and its table sets out how each booking is checked. The criteria leave open whether anything else a direct edit does also applies, and what "significant" covers.

## Decision
1. **One code path.** `_apply_and_reassess` applies the values and does everything a change unsettles, without committing: the history entries, the withdrawal, the flags, the return to Approved in Safety Review, and the equipment. `_tell_of_applied_change` sends the notices after the commit. `update_event_request` and `decide_change_request` both call them, so an edit and an approval can't drift apart. Nothing about the flags, their wording or the gates changes, so there is no new migration, column or notification kind.
2. **A rejected request, or an approval refused as stale or invalid, reassesses nothing** (SCRUM-57 AC3, AC8). The flags, the withdrawal, the change and the decision share one commit, so a failure in any of them saves none of them.
3. **Default: "significant" is what SCRUM-33 AC2 lists, equipment requirements included.** SCRUM-58's definition names the date, start or end time, expected attendance and venue requirements, and cites SCRUM-33 AC2, which also names equipment requirements. AC6 says the rule is SCRUM-33 AC7's, and a direct edit of equipment requirements withdraws an approval, so an approved one does too: a Confirmed event goes back to Approved. The venue bookings stay untouched (AC4). This is a question for the Product Owner.
4. **Default: a Confirmed event goes back to Approved only through the withdrawal** (AC7, ADR-0087, ADR-0094 decision 11), with no status change of its own. Confirmation needs an approval and every withdrawal leaves Confirmed, so a Confirmed event always has one. A row saved straight as Confirmed with no approval, which no route can produce, would stay Confirmed.
5. **Default: SCRUM-33 AC9 applies to an approved change too.** SCRUM-58 doesn't mention it, but it runs "the same checks". In Safety Review, a flag sends the event back to Approved even with no approval to withdraw, and every Safety Officer is told, naming the fields changed.
6. **Default: nobody new is told of the return to Approved.** The Organiser gets `change_request_approved` and sees the status on the record, as ADR-0087 decision 3 leaves it; Attendees hear only of a new date or time (SCRUM-57 AC7). Registrations stay, the event leaves the catalogue until it is confirmed again (ADR-0087 decision 2), and a registered Attendee's page says its arrangements are being reviewed (ADR-0109 decision 12). Venue Staff are told per booking flagged, Technical Support once, and the coordinator who approved it isn't told (ADR-0094 decision 7).
7. **The journey goes past AC8's end.** AC8 stops at Venue Staff reconfirming. `tests/e2e/test_change_request_venue_journey.py` goes on to Technical Support confirming the reservation, a new Safety Review and a second confirmation, because that is what AC7 says must happen.
8. **The mock's approval does what its edit does.** Both go through `applyAs`. The mock takes a Confirmed event to hold an approval, since its Confirmed events have no planning record to say so. As with its edit, it raises no notices and leaves the equipment mock alone (ADR-0107 decision 10).

## Consequences
- A Confirmed event's approved change of date, time, attendance, venue requirements or equipment requirements closes its registration until it passes a new Safety Review and is confirmed again.
- SCRUM-59's pre-filled period and occupancy work unchanged, because an approved change writes its `field_changed` entries as an edit does (ADR-0112's consequences).
- The SCRUM-57 test that a Confirmed event stays Confirmed after a date or time change is gone: it set the status with no approval, which can't happen.

## Questions for the Product Owner
1. Should an approved change to the equipment requirements alone send a Confirmed event back to Approved (decision 3)? SCRUM-58's definition leaves it out; SCRUM-33 AC2, which the definition cites, includes it.

## Revisit when
- The Product Owner answers the question above.
- The customer answers ADR-0087's question about whether a changed Confirmed event should stay Confirmed with its preparation on hold.
