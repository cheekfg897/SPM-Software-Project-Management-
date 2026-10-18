# ADR-0082: Venue Staff hold, move and decide tentative holds from their booking queue

- **Status:** Accepted; offering the hold on every waiting request, the coordinator seeing the
  expiry on the venue requests page, and asking for the expiry as a Singapore date and time are
  defaults to review with the Product Owner
- **Date:** 2026-10-19
- **Story:** SCRUM-75 Place a tentative hold on a venue; SCRUM-94 Expire tentative holds
  automatically (the expiry the coordinator sees)
- **Builds on:** ADR-0035, ADR-0042, ADR-0045 (decisions 13 to 18), ADR-0052

## Context
The backend for holds is on main (ADR-0045, ADR-0052): `POST
/api/venues/booking-requests/<id>/hold` places a hold with an `expires_at`, `PATCH` on the same
route moves it, and the decision route gives final approval to, or rejects, a request On Hold.
Venue Staff's queue (`GET /api/venues/booking-requests`) already lists On Hold requests beside
the Pending and Conflicting ones, each with its `hold_expires_at`. None of it had a screen. The
ACs, the backend and the earlier ADRs leave a few things open for the web app:

1. **Which requests offer a hold.** A hold applies only to a multi-venue event (AC1), which the
   backend checks by counting the event's active arrangements. The queue does not send that
   count.
2. **How the expiry is typed.** The backend takes any date-time; one without an offset is read
   as business time (ADR-0009).
3. **Where the coordinator sees the hold (AC9).** The AC says "on the event record". The
   coordinator's event page shows the event and links to its "Venue requests" page, where the
   requests, with their statuses and actions (SCRUM-93), are listed.
4. **AC6** (Tentative on the venue availability calendar, and the venue left out of search).
   The calendar is on main (SCRUM-26, SCRUM-34, ADR-0068), and the backend's venue search
   already leaves out a venue a live hold occupies (ADR-0045 decision 17).

## Decision
1. **Each request in the queue shows its status** (Pending, Conflicting or On hold), so Venue
   Staff can tell a request waiting for a first decision from one waiting for final approval.
2. **Every Pending or Conflicting request offers "Place hold"** beside Approve and Reject, with a
   required "Hold expiry" date and time. Whether the event has more than one venue is the
   backend's rule: a single-venue request's hold is refused with the backend's message ("A hold
   can only be placed on a request of an event with more than one venue."), shown on the card.
   The screen does not count arrangements itself. **Default to review.**
3. **The expiry is typed as a Singapore date and time** and sent with the `+08:00` offset, as
   the venue request form sends its period. "In the future" and "before the event starts" are
   the backend's rules; their messages show under the field.
4. **A request On Hold shows "Hold expiry" with the date and time** and offers "Change expiry"
   with the same field, and the same Approve and Reject as any waiting request: approving it is
   the final approval that turns the hold into the booking, and rejecting it releases the venue
   (AC7). After any of these the queue is read again, so what it shows is the backend's.
5. **The coordinator sees the hold on the event's venue requests page** (AC9): the request reads
   "On hold" with its "Hold expiry" date and time, and an Expired one keeps the expiry it ran
   out at (SCRUM-94 AC6). The same line shows in Venue Staff's queue, from one component. The
   event page itself does not list venue requests; its "Venue requests" link leads there.
   **Default to review.**
6. **AC6 needs nothing more here.** The venue's calendar already shows a live hold as
   "Tentative", in a colour of its own, apart from a confirmed booking, and leaves an expired one
   off. The mock calendar keeps its own bookings, so a hold placed on the queue in mock mode does
   not appear on a venue's mock calendar; against the backend it does, as both read the same
   bookings.
7. **The notices** (AC9, SCRUM-94 AC3, AC4) need no screen of their own: the notification bell
   and list show what the backend sends.

## Consequences
- Venue Staff can run the whole hold cycle from one page: place, move, approve or reject.
- A Venue Staff member may try to hold a single-venue request and be refused. The refusal says
  why, and a link to the event's arrangements could replace it if the queue ever sends the
  count.
- The mock backend answers the hold routes with the backend's rules and messages, and lists On
  Hold requests in the queue, so the screens and the e2e journey run without a backend.

## Revisit when
- The event page lists its venue arrangements itself: show the hold there too.
- The queue sends whether a request can be held: offer the hold only where it applies.
