# ADR-0032: The event catalogue API, and registering for an event

- **Status:** Accepted. Proposed by the frontend on 2026-09-29; implemented by SCRUM-52 on 2026-10-14. The items marked *default to review* are the team's to confirm.
- **Date:** 2026-09-29
- **Story:** SCRUM-52 Register for a confirmed event (with SCRUM-54 and SCRUM-69 for capacity)

## Context
The web app shows a public catalogue of events that Attendees can search, filter by date and
register for. That is SCRUM-52, a Sprint 3 story. The frontend rule is that the backend is the
source of truth: the frontend never pages, filters, sorts or counts for itself. So the shape of
the backend's answer had to be agreed before the catalogue screen could be built. This ADR
recorded that shape so the frontend could be built against mock handlers; SCRUM-52 implements it
and settles what the shape left open.

Events cannot reach `confirmed` until SCRUM-49, and registration is enabled by SCRUM-69
(ADR-0043). Until then no event is listed, which is the correct answer, not a gap.

## Decision

### `GET /api/events/catalogue`
Public: no token needed. If a valid token is sent, `is_registered` reflects that user;
otherwise it's `false`. A token that is expired or not valid is read as a visitor rather than
refused, so the page still opens. It lists only **confirmed events with registration enabled**
(SCRUM-52 AC1), **soonest first**, and never events that have already ended: an event whose end
is now or earlier is left out.

Query parameters, all optional:

| Parameter | Meaning |
|---|---|
| `q` | Search text, matched case-insensitively against the event's name and description. Spaces around it are ignored; blank matches everything. It will match the venue's name too once `venue` is filled in (below). |
| `when` | A preset window on the event's **start**: `upcoming` (the default: everything not yet ended), `today`, `this_week` (today to Sunday), `this_weekend` (the coming Saturday and Sunday, or the rest of it if it's already the weekend). Resolved by the **backend** in business time (ADR-0001), whole days, both ends included. |
| `starts_from`, `starts_to` | A custom range on the event's start, both ends included. Date-times; one sent without an offset is read as business time (ADR-0009), which is what the browser's `datetime-local` input produces. Either end may be left out; the two may be equal. A custom range replaces `when`: sending both is a `400`. |
| `page` | 1-based page number. Default `1`. |
| `page_size` | Default `12`, maximum `50`. |

`200` body:

```json
{
  "items": [
    {
      "id": 41,
      "reference": "EVR-7K2M9Q4A",
      "name": "Jazz by the Bay",
      "description": "An evening of ...",
      "starts_at": "2026-10-03T19:30:00+08:00",
      "ends_at": "2026-10-03T22:00:00+08:00",
      "venue": null,
      "capacity": 200,
      "places_left": 12,
      "is_full": false,
      "is_registered": false
    }
  ],
  "page": 1,
  "page_size": 12,
  "total": 31,
  "total_pages": 3
}
```

- Times come back with an offset in business time, as every other date-time does (ADR-0009).
- `description` is `""` for an event that has none.
- **`venue` is `null` for every event for now.** `main` has no way to find an event's booked
  venue through the venue module's public services, and the events module must not read the
  venue module's models; this is the same wait as ADR-0043's AC3. The shape stays
  `{"id", "name"}` when it arrives (SCRUM-42 and SCRUM-43), and the frontend already shows
  "Venue to be announced" for `null`.
- `places_left`, `is_full` and `total_pages` are the backend's numbers, worked out from the
  real registrations: a place is taken by each registration with status `registered`.
  `places_left` is never below `0`. The frontend shows them as they are and never works them out
  from `capacity` or `total`. `total_pages` is `0` when nothing is listed.
- A `page` past the last page returns an empty `items` with the real `total` and
  `total_pages`, not an error.
- **A full event stays listed,** shown as full, so a place freed by a withdrawal (SCRUM-54 AC3)
  can be taken.

Bad input is a `400 validation_error` whose `details` name the query parameter, e.g.
`{"starts_to": ["Must be after starts_from."]}`,
`{"when": ["Must be one of: upcoming, today, this_week, this_weekend."]}`,
`{"when": ["Send either a preset or a custom range, not both."]}`,
`{"starts_from": ["Not a valid date-time."]}`, `{"page": ["Must be at least 1."]}` or
`{"page_size": ["Must be between 1 and 50."]}`. A parameter that isn't in the table is
`{"<name>": ["Unknown field."]}`.

### `POST /api/events/catalogue/<id>/registrations`
Registers the caller for the event. **Attendees only.**

- **There is no request body: the account is the registration information** (SCRUM-52 AC2).
  Until the customer says otherwise, nothing more is asked for. Adding fields later means a body
  schema here and a form on the card.
- `201` with the registration: `{"id", "event_id", "status": "registered", "registered_at"}`.
- `401 authentication_error`: no token, or an invalid one.
- `403 authorization_error`: signed in, but not an Attendee.
- `404 not_found`: no such event, it isn't confirmed with registration enabled, or it has
  already ended (SCRUM-52 AC4 is the same answer as "not in the catalogue").
- `409 already_registered`: the caller already holds a place (SCRUM-52 AC3). This is checked
  before `event_full`, so someone holding the last place is told they are registered, not that
  the event is full.
- `409 event_full`: no places left (SCRUM-54 AC2). Two attempts at the last place: exactly
  one gets `201` (SCRUM-54 AC4).

The frontend shows each error's `message` as the backend wrote it.

**Two attempts at the last place.** The event's row is locked (`SELECT ... FOR UPDATE`) from
the moment registering reads it until the commit, so the second request counts the registrations
only after the first has committed. A unique constraint on (event, attendee) is the backstop for
one attendee's duplicate: if it ever fires, the answer is still `409 already_registered`.

### `GET /api/events/registrations`
The Attendee's **own** registrations, newest first. **Attendees only** (`401`, `403` as above).
This is SCRUM-52 AC5, "the event appears in their list of registrations", and SCRUM-53 reads the
same list. `200` body:

```json
{
  "registrations": [
    {
      "event_id": 41,
      "name": "Jazz by the Bay",
      "starts_at": "2026-10-03T19:30:00+08:00",
      "status": "registered",
      "registered_at": "2026-09-30T12:00:00+08:00"
    }
  ]
}
```

An event that has since completed or been cancelled is still listed: it is the attendee's
record. SCRUM-53 adds `DELETE /api/events/catalogue/<id>/registrations` for withdrawing and a
`withdrawn` status to this list, rather than a second list.

### Capacity below the registrations (SCRUM-69 AC5)
`PATCH /api/events/requests/<reference>/registration` (ADR-0043) now refuses a capacity lower
than the number of places taken: `400 validation_error` with
`{"registration_capacity": ["Capacity cannot be lower than the 5 places already taken."]}`. A
capacity equal to the number registered is allowed, and the rule applies whether registration is
enabled or not. Turning registration off with attendees registered is allowed.

## Consequences
- The frontend's catalogue (`frontend/src/features/catalogue`) and its mock handlers
  (`frontend/src/mocks/handlers/catalogue.ts`) were built to this; the integration tests that
  can run against a backend with no confirmed event are real now. Those that need a confirmed
  event with registration enabled stay `it.todo` until something can confirm one (SCRUM-49).
- The registration module (`app/modules/registration`) owns the `registrations` table
  (migration 0027). It gets event facts from the events module's public functions only
  (`list_registrable_events`, `get_registrable_event_for_update`, `list_event_headings`), and the
  events module calls the registration module's `count_registered` for SCRUM-69 AC5. The
  events module imports it inside the one function that needs it, because the registration
  module imports the events module.
- The catalogue's searching, date windows and ordering are done in Python over the confirmed,
  registration-enabled events, because an event's start is a date and a time in two columns.
  That is fine for the hundreds of events a catalogue holds, and reads plainly. *Default to
  review.*
- Presets are resolved by the backend, so "today" and "this weekend" follow business time
  whatever the visitor's own clock or time zone says.
- The unit tests run on SQLite, which neither locks a row nor runs two transactions at once, so
  they cannot prove the last-place race. They prove the event row is selected `FOR UPDATE`, that
  the second of two sequential attempts is refused, and that the database's unique constraint
  refuses a duplicate the check missed.

## Open
- **What "registration information" SCRUM-52 AC2 needs,** if the customer wants more than the
  account. Adding fields means a body schema and a form on the card.
- **Withdrawal and the unique constraint (SCRUM-53).** One row per (event, attendee) means a
  withdrawn attendee who registers again must have the same row's status set back to
  `registered`, not a new row inserted. SCRUM-53 should take this into account when it adds
  `withdrawn`.
- **Lowering the capacity while someone registers.** Registering locks the event's row, but
  `update_registration_settings` does not, so a capacity lowered in the same instant as the last
  registration could leave one more registration than the new capacity. The catalogue shows
  `places_left` as `0`, never negative. Locking the row in the settings update would close it.
- **A venue in the catalogue** waits for SCRUM-42 and SCRUM-43 (`venue` is `null` until then).

## Revisit when
- SCRUM-42 and SCRUM-43 merge: fill in `venue`, and make `q` match the venue's name.
- SCRUM-53 is picked up: it adds `DELETE`, the `withdrawn` status and the re-registration rule.
- The customer defines SCRUM-52's registration information.
