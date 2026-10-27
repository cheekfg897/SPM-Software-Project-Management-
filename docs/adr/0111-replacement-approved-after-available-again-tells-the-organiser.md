# ADR-0111: A replacement approved after the venue is available again still tells the organiser

- **Status:** Accepted. The team chose this on 27 Oct, to settle a gap the review of PR #145 found. It is a default for the reviewer, not a Product Owner decision: SCRUM-92's criteria are met either way.
- **Date:** 2026-10-27
- **Story:** SCRUM-92 Flag bookings affected when a venue becomes unavailable (AC7, AC8, AC9)
- **Extends:** [ADR-0108](0108-organiser-notice-locked-replacement-period-and-available-again-wording.md) (decision 11), [ADR-0053](0053-flag-bookings-when-a-venue-becomes-unavailable.md) (decision 12)

## Context
ADR-0053 decision 12 lets Venue Staff approve a replacement after the original's venue is available again: the original is still released, because the coordinator asked to replace it. ADR-0108 decision 11 told the organiser of an approved replacement only while the original still had its unavailability flags. That broke on one path:

1. A Confirmed event's booking at Hall A is blocked. The event goes back to Approved, and the organiser is told (AC3).
2. The coordinator raises a replacement at Hall B, which waits as Pending.
3. Venue Staff lift the block. The coordinator and the organiser are told "Hall A is available again … Your original booking stands." (AC8, AC9). Lifting the block deletes the flags.
4. Venue Staff approve Hall B. Hall A is released (AC7), but with no flags left the organiser hears nothing.

So the organiser was told the original stands, and then the event's venue changed without a word. AC9 says the organiser is told "when a replacement venue is approved". There were two ways to fix it:
- refuse to approve a replacement whose original no longer needs replacing;
- treat it as an ordinary approval and tell the organiser.

## Decision
1. **The approval goes ahead, and the organiser is told as for any approved replacement.** The detail and kind are ADR-0108 decision 11's, unchanged. ADR-0053 decision 12 stands.
   - **Why not refuse:** the coordinator chose to replace Hall A and Venue Staff chose to approve Hall B. Hall B is not a downgrade:
     - it was checked against the venue's opening hours, and for suiting the booking's occupancy and layout (or justified), when raised;
     - its period is locked to the original's (ADR-0108 decision 2);
     - it was checked for clashes when approved (SCRUM-44).

     Refusing would add a rule the criteria don't ask for, and get in the way of a deliberate choice. The harm was only that the organiser wasn't told.
2. **The categories are read from the event's history, not the flags.** Each flag's `alternative_venue_needed` history entry keeps its category and the arrangement it flagged, and history is never deleted. `list_unavailability_categories` (events module) returns them for one arrangement, oldest first. The venue module names each once, as before.
3. **"Never unavailable" still means no notice.** A replacement for an arrangement with no such history entry, one flagged only after a change (SCRUM-33), tells the organiser nothing, as ADR-0108 decision 11 has it.
4. **What the categories name:** every category that ever flagged the replaced arrangement, including a block lifted earlier. Before, only the flags still on it were named. Both give the same answer unless the arrangement was flagged, freed and flagged again before being replaced.

## Consequences
- On this path the organiser hears "your original booking stands" and then "Hall B has been approved in its place". Both are true when sent.
- The coordinator who doesn't want the replacement once the venue is free still withdraws it before Venue Staff decide (ADR-0053 decision 12).
- No migration, no API change, and nothing for the frontend: the notifications mock serves only seeded notices (ADR-0108).

## Revisit when
- The team decides a pending replacement should be withdrawn automatically when its original's venue is available again (ADR-0053 decision 12).
- Venue Staff should see, while deciding, that the original's venue is available again.
