# ADR-0045: Approving a booking request is refused when it clashes with a confirmed booking

- **Status:** Accepted
- **Date:** 2026-10-16
- **Story:** SCRUM-44 Prevent the same venue being booked twice (the approval clauses only)
- **Extends:** ADR-0011, ADR-0042

## Context

ADR-0042 decision 11 approved a booking request without looking for another booking at the
venue, and left the check to SCRUM-44. SCRUM-44 has three parts. This ADR covers the first;
the others are separate pull requests.

1. **This slice: refuse an approval that clashes.** The ACs on overlapping confirmed bookings,
   on the setup and turnaround padding, and on conflicts being per venue.
2. **Slice B: the Conflicting status.** A Pending request that overlaps another is shown as
   Conflicting, and every booking whose period a buffer change makes overlap is marked
   Conflicting and listed for Venue Staff.
3. **Holds.** The ACs about tentative holds wait for SCRUM-75, which creates the hold.

## Decision

1. **The check runs when a request is approved, and only then.** `decide_booking_request` asks
   whether the requested period clashes with a confirmed booking at the same venue before it
   makes the booking. A rejection books nothing, so it is never checked.

2. **Two periods clash unless the venue's setup and turnaround separate them.** This is the rule
   `_booking_clash` already applies to venue search (ADR-0011): each event holds the venue from
   its start minus setup to its end plus turnaround, so a request and a booking clash unless
   setup + turnaround fits between them. A booking ending at 12:00 at a venue with 30 minutes of
   each lets the next request start at 13:00, and refuses 12:45. Periods that only touch do not
   clash. No buffer arithmetic was written for this slice.

3. **Only confirmed bookings count.** A cancelled booking holds nothing. A tentative booking
   is a hold, and the hold ACs, including that an expired one does not count, are SCRUM-75's.

4. **The refusal is a 409 that names the booking.** The message says whether the requested
   period overlaps the booking itself or only its padding, and in the second case names the
   venue's setup and turnaround. `details` carries `booking_id`, `in_buffer` and the period the
   booking holds the venue for (`occupied_from`, `occupied_until`: the booking padded by its
   venue's setup and turnaround, in business time as ISO 8601). When several bookings clash, the
   earliest is named. Nothing is saved and the request stays Pending.

5. **Conflicts are per venue, whatever the event.** The query filters on the venue and ignores
   the booking's event, so one event's bookings at two venues never clash with each other, and
   two bookings of one event at the same venue do.

6. **The venue row is locked while the approval is checked.** The request row's lock (ADR-0042
   decision 7) only stops the same request being decided twice. Two different requests for one
   venue would each find the venue free, so `decide_booking_request` first reads the venue
   `FOR UPDATE`, and the lock lasts until the approval commits. The second approval waits, then
   finds the first's booking. The read uses `populate_existing` so the buffers are the current
   ones. **SQLite ignores `FOR UPDATE`, so the unit tests cannot show two approvals queueing.**
   They show the venue is read under the lock; the serialising itself is Postgres's.

## Consequences

- Venue Staff can no longer double-book a venue by approving. ADR-0042's consequence that "the
  approve button can double-book a venue" no longer holds for confirmed bookings.
- A venue's blocks (SCRUM-34) are not checked by an approval. Raising a request already checks
  opening hours, and search leaves out blocked venues, but approving into a block is not in
  SCRUM-44's ACs.
- The frontend shows the 409's `message`. Its mock for the decision route refuses an approval
  that overlaps an approved request at the same venue, without the padding.

## Revisit when

- **Slice B** adds the Conflicting status, which will want the same clash query for Pending
  requests, and the buffer-change re-check.
- **SCRUM-75** adds the hold: an active hold counts as a clash, an expired one does not, and
  approving a request does not clash with its own hold (decision 3).
- Venue blocks should refuse an approval too (Consequences).
