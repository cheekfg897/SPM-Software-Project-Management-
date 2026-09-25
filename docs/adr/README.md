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
| [0011](0011-venue-setup-and-turnaround.md) | Setup and turnaround are set per venue, default to 30 minutes, and pad both events | Accepted | SCRUM-67 |
| [0012](0012-event-status-model.md) | Seven event statuses; `under_review` covers "Under Review / Planning"; visibility beyond the organiser waits on later stories | Accepted | SCRUM-22 |
| [0013](0013-client-organisations-recorded-by-internal-users.md) | Client organisations are recorded by internal users; organisers are linked at registration | Accepted | SCRUM-66 |
| [0014](0014-equipment-type-location-and-quantity.md) | An equipment type is one uniquely named record, held at one venue or one named store | Accepted | SCRUM-27 |
| [0015](0015-in-app-notifications.md) | Notifications are in-app rows, one per recipient, that snapshot their event | Accepted | SCRUM-28 |
| [0016](0016-venue-block-warns-not-refuses.md) | A venue block is saved even over a confirmed booking, and reports what it cuts into | Accepted | SCRUM-34 |
| [0017](0017-suitability-check-takes-requirements.md) | The suitability check takes an event's requirements explicitly; the justification rule waits for booking requests | Accepted | SCRUM-36 |

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
