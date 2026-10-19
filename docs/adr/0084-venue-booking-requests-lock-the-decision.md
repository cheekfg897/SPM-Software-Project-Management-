# ADR-0084: A venue booking request locks the event's decision while it is still one of the event's arrangements

- **Status:** Accepted; counting a withdrawn or released request as gone is a default to review
- **Date:** 2026-10-19
- **Story:** SCRUM-31 Review and decide a submitted request
- **Completes:** [ADR-0028](0028-review-and-decide.md) decision 10, which counted equipment requests only and left a `# TODO: SCRUM-42` for venue booking requests

## Context
SCRUM-31 AC7 says: "Recording a new decision is not permitted once a venue booking request or equipment request exists for the event." When ADR-0028 was written there were no venue booking requests, so `_has_arrangements` counted equipment lines only. SCRUM-42, SCRUM-43, SCRUM-93, SCRUM-75, SCRUM-94 and SCRUM-92 have since merged, and a venue booking request can now be in any of eight statuses: `pending`, `on_hold`, `approved`, `rejected`, `conflicting`, `expired`, `withdrawn` and `released`.

The AC doesn't say which of them count as a request that "exists". The two retired statuses are the open question:

- **`withdrawn`:** the coordinator took the request back before Venue Staff decided it (SCRUM-93, [ADR-0039](0039-venue-arrangements.md)).
- **`released`:** a replacement for it was approved after its venue became unavailable (SCRUM-92, [ADR-0053](0053-flag-bookings-when-a-venue-becomes-unavailable.md)).

Both rows stay in the table only so that the event's history and SCRUM-75's venue count can ignore them.

## Decision
1. **A venue booking request locks the decision while it is active,** that is, in any status but `withdrawn` and `released`. "Active" is the venue module's own word, defined once as `RETIRED_REQUEST_STATUSES` (ADR-0039 decision 3). `_has_arrangements` asks `venue_services.count_active_arrangements`, so the events module still never reads the venue module's models.
2. **Whatever Venue Staff made of it, an active request counts.** A `rejected` or `expired` request stays one of the event's arrangements until the coordinator withdraws it, as SCRUM-97's Safety Review gate already treats it, so it still locks the decision. A `pending` one counts from the moment it is raised.
3. **A withdrawn or released request no longer counts.** This matches equipment: a removed equipment line is deleted, so it stops locking the decision, and a withdrawn arrangement is the venue module's way of removing one. A coordinator who withdraws every arrangement can therefore change the decision again. *Default to review:* the AC's "exists" could be read as "has ever existed", which would keep the lock for good once anything was raised.
4. **Nothing else changes.** The refusal is still `409 decision_locked` with the message ADR-0028 already worded for both kinds ("…an equipment request or a venue booking request."), and it is still checked after the status and before the payload (ADR-0028 decision 11). A first decision is never blocked.

## Consequences
- A coordinator who has raised a venue booking request can't reject the event by changing the decision. To undo the planning, they withdraw the arrangement first, as they would remove the equipment.
- Checking a decision now runs one more query: a count of the event's active arrangements, made only when the event has no equipment request.
- The frontend's mock refuses a locked decision from a flag on its fixture for equipment, and asks the booking mock's own store for venue booking requests, leaving out the same two retired statuses (`frontend/src/mocks/handlers/eventReview.test.ts`). The response is unchanged.
- Tests: `tests/events/test_change_decision.py` (marker `scrum_31`), parametrised over every active and every retired status, so a status added to the enum later is checked too.

## Revisit when
- The team reads AC7's "exists" as "has ever existed": count every request, retired ones included.
- A new retired status is added to `RETIRED_REQUEST_STATUSES`: it stops locking the decision automatically. Check that this is what is wanted.
