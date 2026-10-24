# ADR-0094: A significant change reassesses each venue arrangement on its own and flags only those it affects

- **Status:** Accepted for the flag, the gate and the notice (SCRUM-33 AC6); what "affected" means for each field (decisions 3-5), asking for reconfirmation when attendance rises within capacity (decision 4), clearing a flag by a replacement until SCRUM-59 and keeping flags after an undo (decision 8) were agreed by the Product Owner on 25 Oct (answers 6.1-6.5)
- **Date:** 2026-10-19
- **Stories:** SCRUM-33 AC6; mirrors SCRUM-58 AC1-AC5, which make the same reassessment for an approved change request
- **Extends:** [ADR-0025](0025-event-edits-significant-changes-and-history.md) decision 14 (the venue hook); [ADR-0053](0053-flag-bookings-when-a-venue-becomes-unavailable.md) (a flag beside the arrangement's status, the gates, the replacement); [ADR-0087](0087-withdrawn-safety-approval-returns-the-event-to-approved.md) (a Confirmed event goes back to Approved)

## Context
SCRUM-33 AC2 says a change to the proposed date, start or end time, expected attendance, venue requirements or equipment requirements "is marked significant and raises a reassessment of the affected arrangements". ADR-0025 built that for equipment (Technical Support are notified) and left a `# TODO: SCRUM-58` where the venue would go, because no event had a venue arrangement yet. SCRUM-42 and SCRUM-93 have since given events several arrangements, each with its own period, occupancy and layout.

Week 7 added AC6: "Given an event has several venue arrangements, when a significant change is made, then each arrangement is reassessed separately and only the arrangements the change affects are flagged." SCRUM-58, planned for Sprint 4, says the same for a change that arrives through change review, and its ACs say what the flags are:

- **AC1:** a date or time change marks the booking "requiring reconfirmation", the event returns to Approved, and Venue Staff are notified.
- **AC2:** attendance above the venue's capacity marks the booking "no longer suitable", with capacity named as the reason.
- **AC3:** confirmation is refused while a booking is flagged.
- **AC4:** a change touching none of date, time, attendance or venue requirements leaves the booking untouched.
- **AC5:** each booking is assessed against its own occupancy and layout.

SCRUM-59 (Sprint 4) is where Venue Staff reconfirm or withdraw a flagged booking. The ACs leave open what "affected" means for each field, how a flag is stored and cleared, and what happens at the edges.

## Decision
1. **The flag sits beside the arrangement's status, as SCRUM-92's does.** A new table, `reassessment_flags`, holds one row for each reason a change gave: the arrangement (`booking_request_id`), the `kind` (`requires_reconfirmation` or `no_longer_suitable`, SCRUM-58's words, a Postgres enum `reassessment_flag_kind`) and the `reason`, the sentence Venue Staff are told. Keeping the status means the booking itself stands untouched, as SCRUM-93's customer answer asks ("the system does not update anything automatically"). It is a second table rather than more rows in `alternative_venue_flags` because that table's rows are tied to a block or a deactivation (reactivating a venue deletes every one without a block), carry an unavailability category and period that a change has no value for, and mean "find another venue", where these mostly mean "Venue Staff, check this one again".
2. **What gets flagged is a live arrangement:** Pending, Conflicting or Approved (`FLAGGABLE_REQUEST_STATUSES`, the set ADR-0053 decision 2 flags). An arrangement counts as flagged (`is_flagged_after_change`) only while it is live; once it is released, withdrawn or rejected its flags stay as the record of why. On Hold waits for the same SCRUM-75 follow-up as ADR-0053's.
3. **Default: a date or time change affects every arrangement** with `requires_reconfirmation`, "The event's date or time changed." Each arrangement was booked for a period chosen against the event's timing, SCRUM-58 AC1 flags a booking on any date or time change, and SCRUM-59 AC2 reconfirms by moving the booking "to the new period". The event's proposed date, end date, start time and end time all count.
4. **Default: attendance is judged by each arrangement's own occupancy (SCRUM-58 AC5, SCRUM-93 AC3).**
    - An arrangement whose occupancy covered the whole audience before the change *holds everyone*, so it must hold the new attendance too. A smaller one, such as a breakout room, is not judged against the event's attendance at all.
    - An arrangement that holds everyone and whose occupancy still covers the new attendance (a fall, or a room booked for more) is untouched.
    - One the new attendance outgrows is `no_longer_suitable` when its venue can't hold the new attendance, with the suitability check's own capacity sentence: "Expected attendance of 150 exceeds the venue's capacity of 100." (SCRUM-58 AC2).
    - Otherwise it is `requires_reconfirmation`: "The event's expected attendance rose from 80 to 90, above this arrangement's expected occupancy of 80." Venue Staff approved it for fewer people. This also keeps the rule sound over several changes: an arrangement the attendance outgrew is always flagged, so a later rise can't slip past it.
5. **Default: a venue requirements change affects every arrangement** with `requires_reconfirmation`, "The event's venue requirements changed." The requirements are one free-text field for the whole event, which the system can't check against a venue, so Venue Staff check each one. **Layout** is the arrangement's own (SCRUM-93); the event has no layout an edit could change, so nothing here reassesses it.
6. **One change can give an arrangement several reasons,** one row each, in the order timing, venue requirements, attendance. Each later change adds its own rows, as each block adds its own flag.
7. **The flags ride in the edit's own commit; Venue Staff are told afterwards** (ADR-0015), with one `significant_change` notice per arrangement flagged, to every Venue Staff user: "Venue arrangement 12 at Auditorium: The event's date or time changed. Expected attendance of 150 exceeds the venue's capacity of 100." The existing kind fits ("An event you have arrangements for has changed significantly") and needs no migration. A notice that can't be saved loses only itself. The coordinator made the change and is not notified; the arrangement list shows the flags (decision 10).
8. **Default: a flag clears only when the arrangement stops being live.** Until SCRUM-59 gives Venue Staff "reconfirm" and "withdraw", the coordinator can:
    - raise a replacement for it (`replaces_request_id`), exactly as for a SCRUM-92 flag; approving the replacement releases it (ADR-0053 decisions 10-11);
    - withdraw it if it is still Pending, or Venue Staff can reject it.
    A later edit that undoes the change does not clear a flag: the flag records that the booking was unsettled, and Venue Staff still have to look at it.
9. **SCRUM-58 AC3: the Safety Review gate (SCRUM-97) and confirmation (SCRUM-49) both refuse** while any arrangement is flagged, through the shared `_venue_gaps` (ADR-0051), naming each flag: `Venue arrangement 12 is flagged (no longer suitable): Expected attendance of 150 exceeds the venue's capacity of 100.`
10. **The arrangement list shows the flags.** Each booking request in the coordinator's list and in Venue Staff's queue gains `flagged_after_change` and `reassessment_flags` (`[{"kind", "reason"}]`), so the frontend's types and mocks change with this.
11. **A Confirmed event goes back to Approved** (SCRUM-58 AC1) through the safety approval AC7 withdraws ([ADR-0087](0087-withdrawn-safety-approval-returns-the-event-to-approved.md)). A Confirmed event always holds an approval, since confirmation needs one and every withdrawal leaves Confirmed, and every field that flags an arrangement is significant, so this needs no status change of its own.
    - **SCRUM-33 AC8** (added 19 Oct, built by [ADR-0101](0101-direct-edits-stop-at-confirmed.md)) refuses a direct edit of a Confirmed event and makes Awaiting Clarification and Safety Review editable. Nothing here depends on a Confirmed event being editable: the reassessment runs for whatever status an edit is allowed in. Once AC8 is built, the edit that matters most is one in **Safety Review**, where every arrangement is already Approved. If the Safety Officer has approved the event, the withdrawal sends it back to Approved, as above. If not, it stays in Safety Review, and confirmation waits for the flags to clear (decision 9); a replacement may be raised there (ADR-0053 decision 10). An edit while Awaiting Clarification finds no arrangement, because only an Approved event can have one (SCRUM-42). The test that edited a Confirmed event now edits one in Safety Review.
12. **No history entry of its own.** The edit's `field_changed` entries already record what changed and who changed it (AC4), and the flag rows record what it did to each arrangement. SCRUM-59's reconfirmation or withdrawal is where a decision about a flag is recorded.
13. **Migration `0043_add_reassessment_flags`** adds the type and the table; its downgrade drops both. It revises `0042_add_withdrawal_cut_off`, main's head when this was rebased; whichever open migration merges later re-points its `down_revision`.

### Not covered here
- **The organiser's amendment** (ADR-0029) reassesses nothing at the venue: it only happens while a request awaits clarification, before the event is Approved, and only an Approved event can have an arrangement (SCRUM-42).
- **A replacement at the same venue for an overlapping period** is refused when it is approved, because the original's booking still holds the venue until the replacement is approved (ADR-0045). Moving a booking in place is SCRUM-59 AC2's reconfirmation; until then a time change at the same venue is replaced by another venue, or by the same venue for a period that doesn't overlap the original ([ADR-0100](0100-on-hold-same-venue-and-available-again.md)), or waits for SCRUM-59.

## Questions for the customer
All five were answered by the Product Owner on 25 Oct, agreeing with what is built.
1. Should a change to the event's times flag every venue arrangement, or only those whose booked period the new times no longer cover (a breakout room from 14:00 to 15:00 is unaffected when the event's end moves from 17:00 to 18:00)? (We flag every one.) **Answered (6.1): flag every arrangement on a time change.**
2. When attendance rises but the venue can still hold everyone, should Venue Staff reconfirm the booking, or should it stand? (We ask them to reconfirm.) **Answered (6.2): Venue Staff reconfirm.**
3. Should a change to the event's venue requirements flag every arrangement for reconfirmation? (We do, since the requirements can't be checked automatically.) **Answered (6.3): yes, every arrangement.**
4. Until Venue Staff can reconfirm a booking (SCRUM-59), is replacing it the right way for the coordinator to clear a flag? **Answered (6.4): yes, clear a flag by raising a replacement request.** A replacement may stay at the arrangement's own venue for the event's new time ([ADR-0100](0100-on-hold-same-venue-and-available-again.md) decision 5).
5. If the coordinator undoes a change, should the flags it raised clear by themselves? (They stay.) **Answered (6.5): the flags stay.**

## Consequences
- An Approved event with a flagged arrangement can't go to Safety Review until the flag clears, and today only a replacement, a withdrawal or a rejection clears it; SCRUM-59 adds reconfirmation.
- Every Venue Staff user gets a notice for each arrangement a change flags, across all venues (Venue Staff are not assigned to venues, SCRUM-93).
- `check_venue_suitability` and the reassessment share one capacity sentence (`_capacity_shortfall`), so the reason Venue Staff read matches the search screen's.

## Revisit when
- SCRUM-59 lands: reconfirming updates the booking to the new details and deletes the arrangement's flags; withdrawing releases it.
- SCRUM-58 lands: an approved change request calls the same `flag_arrangements_after_change`.
- PR #93's follow-up (SCRUM-75) flags On Hold arrangements after a change. A venue becoming unavailable already flags them ([ADR-0100](0100-on-hold-same-venue-and-available-again.md)), through its own `UNAVAILABILITY_FLAGGABLE_STATUSES`, so decision 2 still stands.
- ~~The customer answers the questions above (decisions 3, 4, 5, 8).~~ Answered on 25 Oct, as built.
- ~~SCRUM-33 AC8 is built: the Confirmed-event test in `test_reassess_arrangements.py` changes to an edit in Safety Review (decision 11).~~ Done by [ADR-0101](0101-direct-edits-stop-at-confirmed.md).
