# ADR-0010: Opening venue search pre-filled from an event is deferred

- **Status:** Accepted
- **Date:** 2026-09-25
- **Story:** SCRUM-35 Search and filter venues against event requirements (AC5: "The search can be opened from an event with its filters already populated from that event's recorded requirements")

## Context
AC5 asks for venue search to start from an event, with its filters filled in from what the event recorded. But event requests (SCRUM-19) store their venue, accessibility and equipment requirements as **free text**, such as "Main hall with a stage and 3 breakout rooms". Only the dates, times and expected attendance are structured.

The search filters are structured: a minimum capacity, one layout from a fixed list, and lists of facility and accessibility items. There's no reliable way to turn the free text into those, and guessing would put wrong filters in front of a coordinator without saying so.

## Decision
- AC5 is **not built** in SCRUM-35's first delivery. AC1–AC4 are delivered.
- Search takes every filter explicitly (`POST /api/venues/search`), so a client can already pass an event's dates, times and expected attendance as `start_time`, `end_time` and `min_capacity` itself.
- No partial pre-fill is added: filling in capacity and times but silently dropping the requirements would look complete when it isn't.

## Consequences
- SCRUM-35 can't be closed on this delivery alone. It needs AC5 split into its own ticket or left open.
- The review checklist will keep listing AC5 as missing until then; this ADR is the recorded reason.

## Revisit when
- Event requests record structured requirements (layout, facilities, accessibility), for example once the "request becomes a booking" work needs them. Pre-filling then becomes a straight mapping from the event's fields to the search's.
