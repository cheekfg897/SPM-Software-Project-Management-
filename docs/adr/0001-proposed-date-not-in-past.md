# ADR-0001: "Past" proposed date means before today, Singapore time

- **Status:** Accepted
- **Date:** 2026-09-15
- **Story:** SCRUM-19 Submit an event request (AC3: "Cannot submit a proposed date in the past")

## Context
The AC doesn't say whether today counts as "the past", or which timezone defines "today". The server may run in UTC, but ConnectSphere operates in Singapore. Between 00:00 and 08:00 Singapore time, UTC is still on the previous day, so a server-local check would give the wrong answer.

## Decision
- A proposed date is rejected if it is **strictly before today**. Today is allowed.
- "Today" is the current date in the configured application timezone, which defaults to `Asia/Singapore` and is set by the `APP_TIMEZONE` config value.
- Only the date is checked. A request for today whose start time has already passed is still accepted.
- The validation receives "today" as an input and doesn't read the clock itself, so tests can pin the date.

## Consequences
- Tests are deterministic: they pass a fixed `today` and never depend on the real date.
- `zoneinfo` needs the IANA timezone database, which Windows and slim Docker images don't ship. Add the `tzdata` package to `requirements.txt`.
- Same-day requests are allowed, even though planning them may not be realistic.

## Revisit when
- The business sets a minimum lead time, such as "at least 14 days ahead". That would supersede this ADR.
- ConnectSphere operates across several timezones, in which case "today" should follow the venue's timezone.
