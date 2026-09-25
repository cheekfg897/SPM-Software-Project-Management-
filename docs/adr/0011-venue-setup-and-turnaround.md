# ADR-0011: Setup and turnaround are set per venue, default to 30 minutes, and pad both events

- **Status:** Accepted
- **Date:** 2026-09-25
- **Story:** SCRUM-67 Record setup and turnaround time for a venue

## Context
SCRUM-67 leaves an open question for the customer: *is turnaround time fixed company-wide, set per venue, or dependent on event type or room layout, and what is the default?* The feature can't wait for the answer, because SCRUM-35 (search) and SCRUM-44 (conflict detection) both depend on it. This ADR is the interim answer; the rest of it doesn't depend on the customer.

Review of PR #10 also found three problems with the first version:
1. The columns were nullable with no backfill, and the code had no `NULL` branch, so every venue created before the migration made the calendar and search return a 500.
2. A search padded the existing booking but not the period being asked about. It under-detected conflicts by exactly the setup time: an event could be offered a venue whose previous event was still turning around.
3. The calendar filtered on raw times but returned padded ones, so a booking whose padding reached into the range was missed.

## Decision
- **Per venue**, as `setup_minutes` and `turnaround_minutes` on the venue, both `NOT NULL` and never negative.
- **Default:** a venue created without them takes `DEFAULT_VENUE_SETUP_MINUTES` / `DEFAULT_VENUE_TURNAROUND_MINUTES` from config, 30 each, stored on the venue at that moment. Changing the config later doesn't change existing venues. Migration `0005` gives venues that already exist 30 each.
- **What a booking occupies:** from `start - setup` to `end + turnaround` of its venue.
- **Both sides are padded:** in search (and in SCRUM-44's conflict detection when it lands), the requested event is padded the same way as the existing booking. Two events at a venue therefore need `setup + turnaround` between them: after an event ending at 10:00 with 30/30, the next one can start at 11:00.
- **Blocked periods aren't padded:** maintenance isn't an event, and needs no setup or turnaround of its own.
- **The calendar** widens its query range by the venue's buffers, and shows each booking as its padded period, with the event's own start and end alongside so a coordinator can tell setup from the event.
- **Changing a buffer** leaves bookings as they are (AC4). Pairs of *confirmed* bookings that now overlap come back as `overlap_warnings` on the `PATCH` response, each with the overlapping window. Tentative holds aren't checked.

## Consequences
- No code path handles a venue without buffers, so the `NULL` crash can't recur.
- Search needs two queries: the padding differs per venue, and doing the date arithmetic per row in SQL isn't portable between Postgres and SQLite (the test database).
- Buffers that depend on event type or room layout aren't supported.

## Revisit when
- The customer answers SCRUM-67's open question. If buffers depend on event type or layout, they move from the venue to (venue, event type) and this ADR is superseded.
- SCRUM-44 (conflict detection) lands. It should reuse the same "occupied" rule, not redefine it.
