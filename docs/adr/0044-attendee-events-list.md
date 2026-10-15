# ADR-0044: An Attendee's events list is their registrations, split into upcoming and past

- **Status:** Accepted; keeping completed and cancelled events in the list is a default to review
  with the Product Owner (SCRUM-24 AC7 says "confirmed")
- **Date:** 2026-10-15
- **Story:** SCRUM-24 See the events my role is involved in (AC7, AC8, AC11), with SCRUM-52 AC5
- **Extends:** ADR-0026, ADR-0032

## Context
SCRUM-52 added `GET /api/events/registrations` (ADR-0032): an Attendee's own registrations,
newest first, for SCRUM-52 AC5, "the event appears in their list of registrations".

SCRUM-24 gives every role a list of its events, and its Attendee list is the same thing. As
numbered in Jira on 2026-10-15: AC7 "An Attendee sees the confirmed events they have registered
for", AC8 "Every list shows event name, date, time and status", and AC11 "A role with no events
matching its filter is shown a message saying there are none, rather than an empty list".
ADR-0026 left AC7 for SCRUM-52 ("SCRUM-52 lands: add the Attendee's list"), and a TODO above the
events module's list routes still waits for it.

The list as SCRUM-52 shipped it falls short of SCRUM-24 in three places, and the web app's screen
needs a fourth:

1. **Status.** A row's `status` is the registration's (`registered`), not the event's, so a
   cancelled event looks the same as one that is going ahead (AC8).
2. **None.** An empty list is `[]` with no message (AC11, and ADR-0026's point 7).
3. **Which events.** AC7 says "confirmed" events, but ADR-0032 keeps completed and cancelled ones
   as the attendee's record.
4. **Upcoming and past.** The screen follows the catalogue's Luma-style layout: an Upcoming/Past
   toggle and a timeline by event date. The frontend may not filter or sort for itself
   (`frontend/CLAUDE.md`), so the split and the order have to come from the backend, and "newest
   registration first" doesn't fit a timeline.

## Decision
1. **One list.** `GET /api/events/registrations` is both SCRUM-52 AC5's list and SCRUM-24 AC7's.
   No second route. The TODO above the events module's list routes stops naming the Attendee's.
2. **`when` splits it**, as an optional query parameter:
   - `upcoming` (the default): events that haven't ended, which is what the catalogue's own
     `upcoming` means. An event has ended once now is at or after its end. Soonest start first.
   - `past`: events that have ended. Most recent start first.
   - Ties are broken by the event's id, in the same direction.
   - Any other value is a `400` on `when`, and a parameter it doesn't know is a `400`
     "Unknown field.", as on the catalogue.
3. **Every row carries the event's status, as `event_status`**, and its end, as `ends_at`, next to
   the fields it already had. `status` stays the registration's (`registered`, and SCRUM-53 adds
   `withdrawn`), so ADR-0032's field keeps its meaning. `event_status` uses the event's own
   values (`confirmed`, `completed`, `cancelled`, ...).
4. **An empty list says so.** `message` is "You have no upcoming events." or "You have no past
   events.", and is there only when the list is empty (ADR-0026's point 7). The key stays
   `registrations`, not ADR-0026's `event_requests`, because the rows are registrations, with
   `registered_at`, not event requests.
5. **Completed and cancelled events stay listed**, with their status. A cancelled event stays
   under Upcoming until its date passes, so the attendee sees that it was cancelled instead of
   watching it disappear. *Default to review:* AC7 says "confirmed".
6. **An Attendee lands on their own events after logging in or signing up**, as Luma opens on
   yours. A new attendee sees the empty Upcoming list's message and a link to browse; the
   catalogue is also the header's Events link. A `next` page still wins: someone sent to log
   in from a page goes back to it.

`200` body:

```json
{
  "registrations": [
    {
      "event_id": 41,
      "name": "Jazz by the Bay",
      "starts_at": "2026-10-20T19:30:00+08:00",
      "ends_at": "2026-10-20T22:00:00+08:00",
      "event_status": "confirmed",
      "status": "registered",
      "registered_at": "2026-10-15T12:00:00+08:00"
    }
  ]
}
```

and when there are none:

```json
{ "registrations": [], "message": "You have no upcoming events." }
```

## Consequences
- An Attendee's home is "My events", not the catalogue (`roleHome.ts`); SCRUM-6's landing
  tests follow.
- The web app's "My events" page sends the toggle as `when`, keeps it in the URL, groups the rows
  by day as the catalogue does, shows `event_status` as a status chip, and shows `message` when
  the list is empty.
- ADR-0032's "newest first" for this list is replaced by the order above.
- The events module's public `EventHeading` gains the event's end and status. The status is its
  plain value, so the registration module still never imports the events module's models.
- The split and the order are done in Python over one attendee's registrations, which are few.

## Revisit when
- The Product Owner answers AC7: confirmed events only, or every event the attendee registered for.
- SCRUM-53 adds `withdrawn`: decide whether a withdrawn registration stays in its tab with that
  status (ADR-0032 says it does).
- An attendee's list grows long enough to need paging.
