# ADR-0008: Venue opening hours are weekly periods, Google-Places style; overnight allowed

- **Status:** Accepted
- **Date:** 2026-09-22
- **Story:** SCRUM-25 Update venue catalogue (AC1: Venue Staff can edit operating hours)

## Context
AC1 says Venue Staff can edit "operating hours" but doesn't say what shape they take. The first version stored one `operating_hours_start` / `operating_hours_end` pair for every day. That caused three problems:
1. **Overnight venues were impossible.** Create rejected an end time before the start time, so a venue could not be open 18:00 to 02:00. [ADR-0002](0002-event-time-window.md) already allows overnight *events*, so an overnight gala could never fit in any venue.
2. **Every day had the same hours.** A venue couldn't be closed on Sundays, open late on Fridays, or close for lunch.
3. **A PATCH could save end-before-start.** The start/end check only ran when a request sent both fields.

Options considered:
- **A. Keep one start/end pair, and treat `end <= start` as "closes the next day".** No schema change. But, as with option B in ADR-0002, a typo like 14:00 to 13:00 quietly becomes a 23-hour day, and problem 2 remains.
- **B. Seven fixed day slots** (`monday_open`, `monday_close`, ...). Handles closed days, but not split hours, and overnight is still implicit.
- **C. A list of periods, modelled on Google Places `opening_hours.periods`.** Each period has an `open` day/time and a `close` day/time, so overnight hours are written out explicitly.

## Decision
Option C.

**API shape:**
```json
"opening_hours": [
  {"open": {"day": "monday", "time": "09:00"}, "close": {"day": "monday", "time": "18:00"}},
  {"open": {"day": "friday", "time": "18:00"}, "close": {"day": "saturday", "time": "02:00"}}
]
```
- `day` is a lower-case weekday name. `time` is 24-hour `HH:MM`.
- A day with no period is a closed day. Several periods on one day give split hours.

**Validation (replaces "end must be after start"):**
- `close.day` must be `open.day` or the day after. Sunday → Monday wraps around.
- If it is the same day, the close time must be after the open time. Equal times are a zero-length period and are rejected.
- If it is the next day, the close time must be at or before the open time, so a period lasts **at most 24 hours**. Monday 00:00 → Tuesday 00:00 means open all day Monday. 24/7 is seven such periods back to back.
- Periods must not overlap on a weekly timeline that wraps Sunday night into Monday morning. Periods that only touch (one closes at 12:00, the next opens at 12:00) are fine.

This is the same idea as ADR-0002: overnight is stated explicitly with a day, not guessed from the times, so typos are still caught.

**Storage:** a child table `venue_opening_periods` (`open_day`, `open_time`, `close_day`, `close_time`). Days are stored as 0–6 with Monday = 0, matching Python's `date.weekday()`. Times use the `TIME` type, as event requests do.

**Updates:** `opening_hours` in a PATCH replaces the whole weekly schedule. Every request is validated on its own, never merged with saved hours, which removes problem 3.

**Default:** if `opening_hours` is left out on create, the venue is open every day 09:00 to 18:00 (the old default). An empty list means closed every day.

## Consequences
- The rules live in `app/modules/venue/opening_hours.py` as pure functions, independent of the schema, so later availability checks can reuse the weekly timeline.
- Overlap errors are keyed by list position (`{"opening_hours": {1: ["Overlaps opening period 0."]}}`), like marshmallow's own per-item errors, so a client can highlight the row.
- Partial updates pass the top-level field names as `partial` rather than `True`. `True` would also relax required fields inside each period.
- Hours are wall-clock times in the business timezone (`APP_TIMEZONE`), like the rest of the system.
- Not modelled: public holidays, one-off closures and date-specific hours (Google's `special_days`).

## Revisit when
- Venue Staff need holiday or one-off hours.
- Venue booking needs to check an event against opening hours. That check should use this timeline, together with the full start/end datetimes from ADR-0002.
- A venue genuinely needs a single period longer than 24 hours.
