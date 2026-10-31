# ADR-0042: Venue Staff decide a Pending booking request from one queue; approving books the venue and tells the coordinator

- **Status:** Accepted; who is told of a decision changed to the event's current coordinator, not the one who raised the request, by [ADR-0121](0121-venue-decision-notices-go-to-the-current-coordinator.md) (SCRUM-115)
- **Date:** 2026-10-14
- **Story:** SCRUM-43 Approve, hold or reject a venue booking

## Context

SCRUM-43 gives Venue Staff the decision [ADR-0035](0035-venue-booking-requests.md) deferred:
see the requests waiting for them, approve one (which books the venue) or reject it with a
reason, and tell the coordinator who raised it. ADR-0035 decision 13 also left Venue Staff
with no way to *read* a request at all — both of SCRUM-42's routes are coordinator-only — and
named this story as the place to fix it.

The acceptance criteria were rewritten on 2026-10-13 at 13:16, after a customer clarification,
and now describe a hold as an alternative to approval for multi-venue events. The hold itself,
its expiry and its conversion are SCRUM-75; refusing an overlapping period is SCRUM-44. Both
were unstarted when this story was built, so this ADR records where each seam sits.

## Decision

1. **The queue is one list of every Pending request, ordered by event date.** Any Venue Staff
   member sees all of it: staff are not assigned to particular venues (ADR-0035 decision 1, now
   confirmed by the product owner). The order is the event's date, then its start time, then the
   request's id, so the same queue read twice is in the same order.

2. **The ordering is done in Python, not in SQL.** The date is the *event's*, which lives in the
   events module, and a module never joins across another's tables. `list_pending_booking_requests`
   reads the Pending requests, asks the events service for their events in one call, and sorts the
   pairs. The queue is the set of undecided requests, so it is small; if it ever needs paging, the
   page has to come from a single module's query and this decision has to be revisited.

3. **The events module gains two additive items.** `get_events_for_booking(event_ids)` returns the
   events behind a set of requests, by id, with no coordinator check: whoever may read the queue may
   read the events on it. An id with no event is left out rather than raising, so one deleted event
   cannot hide the whole queue. `record_venue_booking_decided(event_id, outcome=...)` writes the
   history entry. The existing `EventForBooking` mapping, which was inline, is now the private
   `_for_booking` so both readers share it.

4. **`outcome` crosses the module boundary as a string, not an enum.** The venue module may not
   import `events.models`, where `DecisionOutcome` lives, so `record_venue_booking_decided` takes
   `outcome: Literal["approved", "rejected"]` and maps it to the history kind inside the events
   module. The alternative, two near-identical `record_venue_booking_approved` and
   `..._rejected` wrappers, duplicates twelve lines to avoid a typed two-value string.

5. **The venue module has its own `BookingDecision` enum**, with the same two values as the events
   module's `DecisionOutcome`, for the same boundary reason. Unifying them means moving the enum
   into `app.common` and changing every caller in both modules, which is a refactor rather than
   part of this story. **Revisit** if a third module needs it.

6. **The decision payload copies SCRUM-31's**: `{"outcome": "approved" | "rejected", "reason": ...}`,
   where a reason is required to reject, optional to approve, must not be blank and is trimmed. The
   route is `POST /api/venues/booking-requests/<id>/decision`, and the queue is
   `GET /api/venues/booking-requests`. Both are keyed by the request's own id, not by the event's
   reference, because Venue Staff work across events and a request is what they decide; ADR-0004's
   reference is for routes a coordinator or organiser reaches through their event.

7. **Only a Pending request can be decided, and the row is locked while it is read.** Anything
   else is a `409` naming the status it is in (the shape SCRUM-93 uses to refuse withdrawing a
   decided arrangement), and an unknown id is a `404`. The status check is a read followed by a
   write, so without a lock two Venue Staff deciding the same request at the same moment would
   both see it Pending and both book the venue. The read takes `with_for_update()` and
   `populate_existing=True`, the seam [ADR-0037](0037-equipment-availability-and-reservation.md)
   established for counting free equipment, so the second decision waits and then sees the first.
   Changing a decision is not in the ACs, unlike an event request's (ADR-0028): a booking has
   been made, and un-making it is SCRUM-61's and SCRUM-92's ground.

8. **Who decided and when live in the event's history, not on the request.** The request gains one
   column, `decision_reason`, because AC6 asks for the reason to be visible. The history entry
   already records the actor and the time, which is where ADR-0035 decision 8 put the request's own
   audit trail, so a second copy on the row would be two sources for one fact. **A default to
   review:** a later story that lists "decided by" beside a request will want `decided_by` and
   `decided_at` columns rather than a history lookup.

9. **The decision, its booking and the history entry are saved in one commit; the notification is a
   second.** This is ADR-0015's ordering and ADR-0035 decision 8's transaction boundary: there is
   never a booking without its history entry. A notification that cannot be saved is rolled back and
   logged, because the venue is already booked and failing the reply would invite a second decision.

10. **The notify-then-roll-back-and-log block is now shared.** ADR-0035's consequences flagged it as
    a near copy of one in the events module and left extracting it as a follow-up. It has a second
    caller in this module now, so it is `_notify_about_booking` here. Moving it into
    `notifications.services`, shared with the events module's copy, is still the follow-up.

11. **No conflict check when approving.** AC3 says approving creates the confirmed booking, and
    every overlap rule — the setup and turnaround padding, identifying the conflicting booking,
    marking other Pending requests Conflicting — is SCRUM-44's story, which also owns the hold-aware
    clauses. The team decided to keep this story to its own ACs rather than pre-empt them.
    **Amended by [ADR-0045](0045-refuse-an-approval-that-clashes.md):** an approval is now refused
    when it clashes with a confirmed booking; the Conflicting status and the hold clauses are still
    to come.
    **Consequence:** until SCRUM-44 merges, two events can be approved into one venue for
    overlapping periods, and nothing warns Venue Staff. The helpers SCRUM-44 needs (`_occupied`,
    `_booking_clash`) already exist, so the change is small when it comes.

12. **`on_hold` is not in the status enum, and `cancelled` is not either.** Postgres keeps every
    value an enum has ever had, so values arrive with the code that produces them (ADR-0035
    decision 3). SCRUM-75 adds `on_hold`; whichever story first cancels a request adds `cancelled`.
    The forward-looking comments in `BookingRequestStatus` and `RETIRED_REQUEST_STATUSES`, which
    promised this story would add `cancelled`, were corrected.

13. **Three of SCRUM-43's own ACs are deferred, each to a named story**, the way ADR-0035 decision 13
    deferred SCRUM-42's:
    - AC1's "and On Hold request, showing its expiry", AC5's conversion of a hold into the booking,
      and AC8's "one request On Hold while another is Approved": **SCRUM-75**, which creates the
      status, the expiry and the hold.
    - AC9, releasing a flagged booking when its replacement is approved: **SCRUM-92**, which links a
      replacement to the booking it replaces.

14. **The frontend queue is a Venue Staff page at `/venue-requests`**, in the existing `booking`
    feature beside SCRUM-42's page. Approving and rejecting are one mutation against one endpoint,
    and the reason field appears for a rejection, because that is the outcome that needs one.

15. **`decision_reason` is added to the booking request response** for every reader, so the
    coordinator's own list (SCRUM-42's route) shows the decision too. The mock handlers, the
    integration test and the two backend tests that assert the whole body were updated in the same
    change (`backend/CONVENTIONS.md` §14).
16. **A rejected arrangement can be withdrawn, and so is retired by cancel-all.** A rejection
    keeps the arrangement active on purpose, because the event can neither enter Safety Review nor
    be confirmed until the coordinator withdraws it (the story's own AC). ADR-0039 decision 4 let
    only a Pending arrangement be withdrawn, which would leave a rejected one stuck for good, so
    withdraw now takes Pending or Rejected and amends that decision. An Approved arrangement is
    still refused with a 409: it has made a booking, and cancelling a booking is in no story yet,
    so cancel-all is refused while an event has an approved arrangement.

## Consequences

- Venue Staff can finally read a booking request, which ADR-0035 decision 13 left undone.
- A booking made by an approval is an ordinary `Booking` row: nothing on it says which request
  made it. The history entry's details carry `booking_id`, which is how a later story can trace
  one. SCRUM-75's conversion of a hold will want that link in the other direction too.
- The queue reads every Pending request before sorting, so its cost grows with the number of
  undecided requests rather than with the page size. That is the trade for decision 2.
- Downgrading migration 0025 deletes decided requests and leaves their bookings, which the
  migration's docstring spells out. CI replays downgrade then upgrade, so the path is exercised.
- Until SCRUM-44 lands, the approve button can double-book a venue (decision 11).

## Revisit when

- **SCRUM-75** adds the hold: the `on_hold` status, the expiry on the queue, converting a hold into
  the booking on approval, releasing it on rejection, and widening
  `uq_venue_booking_requests_pending` to cover On Hold as well as Pending (SCRUM-42's AC was changed
  to "a second Pending **or On Hold** request" on 2026-10-13).
- **SCRUM-44** adds the conflict rules, including the ones about holds.
- **SCRUM-92** links a replacement request to a flagged booking and releases it on approval.
- A story needs "decided by" or "decided at" on the request row (decision 8).
- A third module needs an approve/reject outcome enum (decision 5).
