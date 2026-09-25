# ADR-0016: A venue block is saved even over a confirmed booking, and reports what it cuts into

- **Status:** Accepted
- **Date:** 2026-09-25
- **Story:** SCRUM-34 Block a venue for maintenance or internal use

## Context
SCRUM-34 lets Venue Staff block a venue for a period with a reason. The `venue_blocks` table, the calendar (SCRUM-26) and search (SCRUM-35) already exist and treat a block as "unavailable"; this story adds creating and removing blocks. The story leaves several things open:
1. AC2 says that when a confirmed booking overlaps the period, staff "would be able to see that he is blocking a current booking". It doesn't say whether the block is refused, or which bookings count.
2. Whether a block must fall within the venue's opening hours (ADR-0008).
3. Whether a block in the past may be recorded (ADR-0001 rejects past *event* dates).
4. What "removed" means, and how staff find the block to remove, since the calendar shows blocks without ids (and hides reasons from other roles).

## Decision
- **Warn, don't refuse.** `POST /api/venues/<id>/blocks` always saves the block and returns `201` with it, plus `conflicting_bookings`: the venue's **confirmed** bookings the block cuts into, in start order. Tentative holds aren't listed, matching AC2's wording and ADR-0011's overlap warnings. Nothing happens to the bookings; deciding what to do with them is the staff member's job.
- **"Cuts into" uses the occupied rule.** A booking holds its venue from `start - setup` to `end + turnaround` (ADR-0011), so a block that covers only a booking's setup window is reported. The block itself isn't padded (ADR-0011). Each conflict shows the booking's id, its event id, and the period it holds the venue, in business time, the same way the calendar shows it.
- **Opening hours aren't checked.** Maintenance is usually done while the venue is closed, and a block states that the venue can't be used, whatever its normal hours are.
- **Not before today.** A block is rejected if it *ends* on a business date before today (the ADR-0001 rule, applied to the end). It may start in the past, so a fault found part-way through can be recorded from when it began. A block that has entirely passed can't make a venue unavailable for anything, so accepting one would most likely hide a typo in the year.
- **Reason is required**, non-blank, trimmed and at most 500 characters. The column is `Text`; the cap is an API rule so a reason stays a note.
- **Removal is a hard delete:** `DELETE /api/venues/<id>/blocks/<block_id>` returns `204`, and the block must belong to the venue in the URL (`404` otherwise). Nothing records who created or removed a block.
- **Staff-only listing:** `GET /api/venues/<id>/blocks` returns the venue's blocks with ids and reasons, in start order, so staff can find one to remove. Other roles keep seeing blocks only through the calendar, as "maintenance".
- Blocks aren't checked against other blocks; two overlapping blocks are harmless.

## Consequences
- The calendar and search already exclude blocked periods, so AC1 and AC3 hold as soon as a block is saved; the tests prove that through the new service rather than re-testing those queries.
- The padded-booking condition now lives in one helper shared by the calendar and the conflict check, so later conflict-detection work has a single rule to reuse.
- A staff member can block over a confirmed booking without anything stopping them; the warning is the only safeguard.

## Revisit when
- The customer wants blocks refused (or bookings moved/cancelled) when they cut into a confirmed booking, or wants tentative holds reported too.
- Blocks need an audit trail (who, when) — add `created_by` in a new migration.
- Venue bookings are checked against opening hours (ADR-0008's revisit trigger); decide then whether blocks join that check.
