# ADR-0045: Clashing bookings: refuse a clashing approval, and mark what overlaps Conflicting

- **Status:** Accepted
- **Date:** 2026-10-16
- **Story:** SCRUM-44 Prevent the same venue being booked twice (the approval clauses and, from decision 7, the Conflicting status)
- **Extends:** ADR-0011, ADR-0042

## Context

ADR-0042 decision 11 approved a booking request without looking for another booking at the
venue, and left the check to SCRUM-44. SCRUM-44 has three parts. This ADR covers the first;
the others are separate pull requests.

1. **This slice: refuse an approval that clashes.** The ACs on overlapping confirmed bookings,
   on the setup and turnaround padding, and on conflicts being per venue.
2. **Slice B: the Conflicting status.** A Pending request that overlaps another is shown as
   Conflicting, and every booking whose period a buffer change makes overlap is marked
   Conflicting and listed for Venue Staff. Decisions 7 to 12 below.
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

7. **Two things can be Conflicting, so two enums gain the value.** The ACs use the word for
   a Pending *request* (AC5) and for a confirmed *booking* (AC7). They are different rows, so
   `booking_request_status` and `booking_status` each gain `conflicting`, in one migration
   (0028).

8. **Approving a request marks the Pending requests that clash with it.** AC5 says that when
   the first of two overlapping Pending requests is approved, the second is marked
   Conflicting before it can be approved. So raising a request marks nothing; once an
   approval has passed decision 1's check, every other **Pending** request at the same venue
   that clashes with the approved one, by the rule of decision 2 (`_clash_window` is the
   setup-and-turnaround widening `_booking_clash` uses, shared so the rule is written once),
   is marked Conflicting. The marks are saved in the approval's own commit, so an approval
   that is refused marks nothing. The approved request itself is not marked. Requests that
   are Approved, Rejected, Withdrawn or already Conflicting are left alone, and a request at
   another venue is never marked, whatever its event. A rejection marks nothing, so the
   other request stays Pending.

9. **A Conflicting request can be rejected or withdrawn, but not approved, and nothing clears
   the status.** AC5 is silent on both. Venue Staff keep it in their queue, with its status
   shown, and can reject it (it stays decidable, or nothing could ever settle it); the
   coordinator can withdraw it. Approving it is refused by decision 1's check, because the
   booking that made it Conflicting is still there. No story cancels a confirmed booking yet,
   so the status does not need to clear. When one does, or when a buffer change or a hold
   (SCRUM-75's "re-evaluated when the hold is approved, rejected or expires") can end the
   clash, re-evaluating Conflicting requests belongs with it.

10. **A buffer change marks the bookings the SCRUM-67 report lists.** `update_venue` marks
    each booking in an `OverlapWarning` (both bookings of a pair) and each booking in a
    `BlockOverlapWarning` as Conflicting, in the same commit as the buffer change, and still
    returns the report. Nothing is deleted or cancelled. Only confirmed bookings are checked,
    as before; tentative holds are SCRUM-75's.

11. **A Conflicting booking still holds the venue.** The status records a problem, not a
    release. Confirmed and Conflicting bookings (`HOLDING_BOOKING_STATUSES`) both count for
    the approval check, for the report of the next buffer change and for the bookings a new
    block cuts into, and the calendar shows a Conflicting booking as a confirmed booking.
    Search already treated every non-cancelled booking as busy.

12. **Nothing clears a Conflicting booking either.** If a later buffer change removes the
    overlap, the booking stays Conflicting until a story says how Venue Staff resolve it. The
    AC says only that the booking is marked and listed.

## Consequences

- Venue Staff can no longer double-book a venue by approving. ADR-0042's consequence that "the
  approve button can double-book a venue" no longer holds for confirmed bookings.
- A venue's blocks (SCRUM-34) are not checked by an approval. Raising a request already checks
  opening hours, and search leaves out blocked venues, but approving into a block is not in
  SCRUM-44's ACs.
- The frontend shows the 409's `message`. Its mock for the decision route refuses an approval
  that overlaps an approved request at the same venue, without the padding. The mock also
  marks the Pending requests at the same venue that overlap an approved one Conflicting, and
  lists and decides Conflicting requests.
- `update_venue` now commits once, after the bookings are marked, instead of committing the
  buffer change first. A failure marking the bookings rolls the change back with it.
- Calendar, search and the approval check treat a Conflicting booking as busy, so marking a
  booking never frees its slot.

## Revisit when

- A Conflicting request or booking should clear itself, or be resolved by Venue Staff
  (decisions 9 and 12).
- **SCRUM-75** adds the hold: an active hold counts as a clash, an expired one does not, and
  approving a request does not clash with its own hold (decision 3).
- Venue blocks should refuse an approval too (Consequences).
