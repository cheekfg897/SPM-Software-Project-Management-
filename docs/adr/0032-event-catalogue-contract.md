# ADR-0032: The event catalogue API, proposed by the frontend ahead of SCRUM-52

- **Status:** Proposed
- **Date:** 2026-09-29
- **Story:** SCRUM-52 Register for a confirmed event (with SCRUM-54 and SCRUM-69 for capacity)

## Context
The web app shows a public catalogue of events that Attendees can search, filter by date and
register for. That is SCRUM-52, a Sprint 3 story. The backend has no catalogue endpoint yet,
and events can't reach `confirmed` until SCRUM-49 or open registration until SCRUM-69.

The frontend rule is that the backend is the source of truth: the frontend never pages, filters,
sorts or counts for itself. So the catalogue screen can only be built once the shape of the
backend's answer is agreed. This ADR records that shape so the frontend can be built now
against mock handlers, and so SCRUM-52's backend has a target.

## Decision

### `GET /api/events/catalogue`
Public: no token needed. If a valid token is sent, `is_registered` reflects that user;
otherwise it's `false`. It lists only **confirmed events with registration enabled**
(SCRUM-52 AC1), **soonest first**, and never events that have already ended.

Query parameters, all optional:

| Parameter | Meaning |
|---|---|
| `q` | Search text, matched case-insensitively against the event's name, description and venue name. |
| `when` | A preset window: `upcoming` (the default: everything not yet ended), `today`, `this_week` (today to Sunday), `this_weekend` (the coming Saturday and Sunday, or the rest of it if it's already the weekend). Resolved by the **backend** in business time (ADR-0001). |
| `starts_from`, `starts_to` | A custom range on the event's start. Date-times; one sent without an offset is read as business time (ADR-0009), which is what the browser's `datetime-local` input produces. Either end may be left out. A custom range replaces `when`: sending both is a `400`. |
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
      "venue": { "id": 3, "name": "Esplanade Outdoor Theatre" },
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
- `venue` is `null` only if a confirmed event somehow has no venue booked; the frontend shows
  "Venue to be announced".
- `places_left`, `is_full` and `total_pages` are the backend's numbers. The frontend shows
  them as they are and never works them out from `capacity` or `total`.
- A `page` past the last page returns an empty `items` with the real `total` and
  `total_pages`, not an error.

Bad input is a `400 validation_error` whose `details` name the query parameter, e.g.
`{"starts_to": ["Must be after starts_from."]}`, `{"when": ["Must be one of: ..."]}` or
`{"page": ["Must be at least 1."]}`.

### `POST /api/events/catalogue/<id>/registrations`
Registers the caller for the event. **Attendees only.** No request body for now.

- `201` with the registration: `{"id", "event_id", "status": "registered", "registered_at"}`.
- `401 authentication_error`: no token, or an invalid one.
- `403 authorization_error`: signed in, but not an Attendee.
- `404 not_found`: no such event, or it isn't confirmed with registration enabled
  (SCRUM-52 AC4 is the same answer as "not in the catalogue").
- `409 already_registered`: the caller already holds a place (SCRUM-52 AC3).
- `409 event_full`: no places left (SCRUM-54 AC2). Two attempts at the last place: exactly
  one gets `201` (SCRUM-54 AC4).

The frontend shows each error's `message` as the backend wrote it.

## Consequences
- The frontend's catalogue (`frontend/src/features/catalogue`) and its mock handlers
  (`frontend/src/mocks/handlers/catalogue.ts`) are built to exactly this. The integration
  tests hold `it.todo` entries for each check above, to become real tests with SCRUM-52.
- **This is a proposal.** SCRUM-52's backend should implement it, or change this ADR, the
  mock handlers and the frontend together in the same pull request.
- Presets are resolved by the backend, so "today" and "this weekend" follow business time
  whatever the visitor's own clock or time zone says.

## Open
- **What "registration information" SCRUM-52 AC2 needs.** Until the customer says, the
  account is the registration: no body. Adding fields later means a body schema here and a
  form on the card.
- **Withdrawal (SCRUM-53)** will want `DELETE` on the same resource, and the Attendee's own
  list of registrations. Not part of this contract yet.
- **Whether a full event stays listed.** Here it does, shown as full, so a place freed by a
  withdrawal (SCRUM-54 AC3) can be taken. Revisit if the customer wants full events hidden.

## Revisit when
- SCRUM-52 is picked up: implement this contract, or update it with the frontend.
- The customer defines SCRUM-52's registration information, or SCRUM-53 needs withdrawal.
