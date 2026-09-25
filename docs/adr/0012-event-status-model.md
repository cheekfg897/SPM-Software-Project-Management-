# ADR-0012: Seven event statuses, `under_review` for "Under Review / Planning", and organiser-only visibility for now

- **Status:** Accepted
- **Date:** 2026-09-25
- **Story:** SCRUM-22 Define the event status model

## Context
SCRUM-22 says an event holds exactly one of Draft, Submitted, Under Review / Planning, Confirmed, Completed, Cancelled, Rejected, and lists who may see it. Three things are open:

1. **The list itself.** "Under Review / Planning" is one item with a slash. SCRUM-31 (review and decide) moves a request to *Under Review* and then to *Approved*, a status SCRUM-22 doesn't list; SCRUM-42 raises booking requests "from an approved event"; SCRUM-68 says SCRUM-22 "lists Completed as one of the nine event statuses", but SCRUM-22 lists seven (eight if the slash means two). The "Ask customer" subtask SCRUM-23 (confirm the exact list and the permitted transitions; can a rejected request be resubmitted; can a cancelled event be reinstated) is still open.
2. **Who can see the status.** Four of the five viewers in the AC depend on relationships that don't exist yet: the organiser's *organisation* (SCRUM-66), the assigned coordinator (SCRUM-30), booking requests and bookings against the event (SCRUM-42/43), equipment requests (SCRUM-37) and attendee registrations (SCRUM-52). Today an event request has only `organiser_id`.
3. **How the status changes.** No story in this sprint performs a transition; `submit` (SCRUM-19) sets `submitted` and nothing changes it afterwards.

Postgres is a constraint too: `event_request_status` is a native enum type. Values can be added (`ALTER TYPE ... ADD VALUE`, which the same transaction can't then use, and which Postgres before 12 refuses inside a transaction at all) but never removed, and CI replays `downgrade base` then `upgrade`.

## Decision
- **Exactly the seven values SCRUM-22 lists**, stored as snake_case in the existing `event_request_status` type and listed in lifecycle order in `EventRequestStatus`: `draft`, `submitted`, `under_review`, `confirmed`, `completed`, `cancelled`, `rejected`.
- **`under_review` is the one value for "Under Review / Planning".** The slash reads as two names for one stage: the coordinator reviews the request and, if it goes ahead, plans it (venue and equipment requests) until it is confirmed. `under_review` is the name SCRUM-31 uses for the transition; "planning" is what happens while a request is in it.
- **No `approved` value yet.** SCRUM-22 doesn't list it and SCRUM-23 is unanswered. When SCRUM-31 is implemented it either treats Approved as "still `under_review`, with the decision recorded in the event's history" or adds `approved` with a one-line `ADD VALUE` migration. That choice, and SCRUM-68's count of nine, belong to SCRUM-23's answer and SCRUM-31's implementer; they are flagged here so they aren't resolved silently.
- **No transition rules and no status-change endpoint.** The stories that move an event own their rules: SCRUM-20 (`draft`), SCRUM-31 (`under_review`, `rejected`), SCRUM-49 (`confirmed`, `rejected`), SCRUM-61 (`cancelled`), SCRUM-68 (`completed`). `submit` keeps setting `submitted`.
- **Visibility today: the organiser who submitted the request**, through the existing list (`GET /api/events/requests`) and a new detail endpoint `GET /api/events/requests/<reference>`, both returning `status`. "The Event Organiser whose organisation owns the event" is read as "the organiser who submitted it" until SCRUM-66 links requests to organisations; that changes one filter (`organiser_id` → the organisation's).
- **Other people's requests are `404`, not `403`.** The lookup is scoped to the caller (CONVENTIONS §12), so a reference belonging to someone else is indistinguishable from one that doesn't exist and the response can't confirm a reference is real (ADR-0004: the reference is not an access control). SCRUM-7's "access is refused" is met by this. The lookup ignores case and surrounding spaces, as ADR-0004 asks.
- **The other four viewers are deferred** to the story that creates each relationship: assigned coordinator (SCRUM-30), Venue Staff with a booking request or booking (SCRUM-42/43), Technical Support with an equipment request (SCRUM-37), registered Attendees (SCRUM-52). Each widens the detail endpoint's allow-list and the service's ownership check; SCRUM-24 owns the per-role lists.
- **Migration 0006** adds the six new values inside Alembic's `autocommit_block`, so they are added outside the migration transaction. **Downgrade** rebuilds the type with only `submitted` (rename, create, re-cast the column, drop the old type) after setting any row in a removed status back to `submitted`: a lossy rollback, but the pre-0006 schema can't hold anything else, and refusing would leave `downgrade base` unusable.

## Consequences
- Code can name every status now (`EventRequestStatus.CONFIRMED`) even though only `submitted` is written; the transition stories need migrations only for their own tables.
- Adding `approved` later is one `ADD VALUE`; renaming or removing a value means a type rebuild like the downgrade.
- `ADD VALUE` appends, so the Postgres type sorts `submitted` before `draft`. Nothing orders by `status`; if something needs lifecycle order, sort in code by `EventRequestStatus`, not with `ORDER BY status`.
- Migration 0006's `ADD VALUE`s commit before the rest of a multi-migration upgrade (Alembic's documented trade-off); nothing else in 0006 depends on them.
- The detail endpoint is organiser-only, so the four other roles get `403` until their stories land.
- `flask db check` doesn't compare enum members; `tests/events/test_event_status_migration.py` checks the migration's value list against the model instead, and renders the migration's SQL offline so the upgrade and downgrade are tested without Postgres.

## Revisit when
- SCRUM-23 is answered: confirm the list, whether `approved` exists, and the transitions (rejected → resubmitted? cancelled → reinstated?). Supersede this ADR if the list changes.
- SCRUM-31 lands and needs `approved`.
- SCRUM-66 lands: switch ownership from `organiser_id` to the organisation.
- SCRUM-30, SCRUM-37, SCRUM-42/43 and SCRUM-52 land: widen the detail endpoint for each role.
