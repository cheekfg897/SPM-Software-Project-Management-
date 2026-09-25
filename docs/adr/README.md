# Architecture Decision Records

Short records of decisions we made where the requirements were silent or ambiguous. We choose a decision so we can move forward, and revisit it when new requirements arrive.

To change a decision, don't rewrite history. Add a new ADR that **supersedes** the old one, and set the old one's status to `Superseded by ADR-XXXX`.

## Statuses
- **Proposed**: drafted, not yet agreed by the team.
- **Accepted**: agreed; code follows it.
- **Superseded**: replaced by a later ADR.

## Index

| ADR | Title | Status | Story |
|---|---|---|---|
| [0001](0001-proposed-date-not-in-past.md) | "Past" proposed date means before today, Singapore time | Accepted | SCRUM-19 |
| [0002](0002-event-time-window.md) | Event time window: end must be strictly after start; overnight allowed through `end_date` | Accepted | SCRUM-19 |
| [0003](0003-expected-attendance-minimum.md) | Expected attendance must be at least 1, with no upper limit | Accepted | SCRUM-19 |
| [0004](0004-event-request-reference-format.md) | Event request reference is a random code like `EVR-XXXXXXXX` | Accepted | SCRUM-19 |
| [0005](0005-password-policy.md) | Passwords need at least 8 characters, a letter and a digit | Accepted | SCRUM-65 |
| [0006](0006-access-tokens.md) | Log in with a 1-hour JWT access token, no refresh token yet | Accepted | SCRUM-6 |
| [0007](0007-authorization-failures-are-logged.md) | A refused request is "recorded" as a structured log line | Accepted | SCRUM-21 |
| [0008](0008-venue-opening-hours.md) | Venue opening hours are weekly periods, Google-Places style; overnight allowed | Accepted | SCRUM-25 |
| [0009](0009-booking-times-in-utc.md) | Booking and block times are stored in UTC and shown in business time | Accepted | SCRUM-26 |
| [0010](0010-search-prefill-deferred.md) | Opening venue search pre-filled from an event is deferred | Accepted | SCRUM-35 |

## Template

```markdown
# ADR-NNNN: Title

- **Status:** Proposed | Accepted | Superseded by ADR-XXXX
- **Date:** YYYY-MM-DD
- **Story:** <user story name / Jira ID>

## Context
What is ambiguous or undecided, and why it matters.

## Decision
What we chose.

## Consequences
What this makes easier or harder; what code/tests depend on it.

## Revisit when
The signal that should make us reopen this.
```
