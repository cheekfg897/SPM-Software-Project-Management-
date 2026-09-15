# ADR-0002: Event time window: end must be strictly after start; overnight allowed through `end_date`

- **Status:** Accepted
- **Date:** 2026-09-15
- **Story:** SCRUM-19 Submit an event request (AC1 fields; AC4: "Cannot submit an end time earlier than the start time")

## Context
Two points are ambiguous:
1. **End time equal to start time.** AC4 only forbids "earlier". A zero-length event isn't meaningful.
2. **Overnight events**, such as a gala from 22:00 to 02:00. The team wants to allow them. With only `proposed_date`, `start_time` and `end_time`, an overnight event *has* an end time earlier than its start time, which AC4 says to reject. The two requirements can't both hold with the AC1 fields alone.

Options considered:
- **A. Add an optional `end_date`** that defaults to `proposed_date`. Compare full date+times.
- **B. Treat `end_time < start_time` as "ends the next day".** There's no new field, but AC4 could never be triggered, and a typo like 14:00–13:00 would quietly become a 23-hour event.
- **C. Disallow overnight events.** This follows AC4 exactly but contradicts the team's intent.

## Decision
**How we read AC4:** "an end time earlier than the start time" means the event must not end before it starts. The comparison uses the full start and end datetimes, not the clock times alone. A request for 22:00 on day 1 to 02:00 on day 2 satisfies AC4.

Option A:
- Add `end_date`, an optional field that defaults to `proposed_date`.
- Start = `proposed_date + start_time`. End = `end_date + end_time`.
- Reject if **End <= Start**. Equal times are rejected as well as earlier ones.
- Reject if `end_date` is before `proposed_date`.
- For a same-day event (no `end_date` sent), this is exactly AC4 plus the equal-time rule.
- There is no maximum duration for now.

## Consequences
- Adds one field beyond the AC1 list. Tell the PO, because it's additive and optional.
- Validation belongs in a schema-level validator, because it compares several fields.
- Error details point at `end_time`, or at `end_date` when the date itself is before the proposed date.
- Later stories on venue availability and scheduling must use the full Start/End datetimes, not the times alone.

## Revisit when
- Requirements set a maximum event duration or a rule for multi-day events.
- Venue booking needs different start and end timezones.
