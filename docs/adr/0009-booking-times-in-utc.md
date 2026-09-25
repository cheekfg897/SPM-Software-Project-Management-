# ADR-0009: Booking and block times are stored in UTC and shown in business time

- **Status:** Accepted
- **Date:** 2026-09-25
- **Story:** SCRUM-26 View a venue's availability calendar (raised in review of PR #8)

## Context
Two representations of time now exist side by side:
- **Event requests** store a `Date` plus separate `Time` fields, meaning wall-clock time in the business timezone (ADR-0001, ADR-0002).
- **Bookings and venue blocks** store `timestamptz` start and end instants, because a booking is a real period on a shared timeline that other bookings are compared against.

Review of #8 found three problems with the second one:
1. A client could send `"2026-01-01T09:00:00"` with no offset. Marshmallow loads that as a *naive* datetime, Postgres returns *aware* ones, and comparing the two raises `TypeError`: a 500.
2. SQLite, the unit-test database, drops timezones entirely, so both sides were naive under test and the bug was invisible.
3. Nothing said how the two representations meet when "an event request becomes a booking" is built.

## Decision
- **Storage:** booking and block times use the `UTCDateTime` column type (`app/common/database.py`). It converts to UTC on the way in and always returns timezone-aware UTC on the way out, including on SQLite. A naive value reaching the database is refused as a bug, not guessed at.
- **Input:** a time with an offset (`Z`, `+08:00`) is converted to UTC. A time **without** an offset is read as business time (`APP_TIMEZONE`, default `Asia/Singapore`), the same rule event requests follow, then converted to UTC. `as_utc()` in `app/common/clock.py` implements this, and every start/end pair goes through the shared `_TimeRangeSchema` in the venue module, so the rule is written once.
- **Output:** responses show times in business time with its offset, such as `2026-10-01T17:00:00+08:00` for 09:00 UTC, using the `BusinessDateTime` field (`app/common/fields.py`). ConnectSphere only operates in Singapore, so clients display what they receive. The timezone lives only in the backend's `APP_TIMEZONE`; no client has to know it or keep its own copy.
- **Requests becoming bookings (future story):** combine `proposed_date` + `start_time` and `end_date` + `end_time` in `APP_TIMEZONE`, then convert with `as_utc()`. Event requests keep their date-and-time form; bookings keep instants.

## Consequences
- Mixing an offset-less time with an offset one in the same request can't crash, because both are converted before they're compared.
- Tests on SQLite now see the same aware UTC values as production, so a naive/aware mix-up fails a test instead of reaching Postgres.
- A client in another timezone that omits the offset gets Singapore time, not its own. The README tells clients to send an offset when they mean anything else.
- Storage, comparison and padding are all in UTC; business time appears only at the edges (reading input without an offset, writing responses). Every response schema showing a booking-related time must use `BusinessDateTime`.

## Revisit when
- ConnectSphere runs venues in more than one timezone (also a trigger in ADR-0001). "Business time" would then come from the venue, not the app, and responses might need to return UTC and let clients convert.
