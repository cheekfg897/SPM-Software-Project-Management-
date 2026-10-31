# ADR-0121: Venue Staff's booking decision is told to the event's current coordinator

- **Status:** Accepted; who is told is the Product Owner's decision (SCRUM-115, 31 Oct)
- **Date:** 2026-10-31
- **Story:** SCRUM-115 Venue decision notices go to the event's current coordinator
- **Supersedes:** [ADR-0042](0042-venue-booking-decisions.md)'s "tell the coordinator who raised it" (its context, and the recipient of decision 9's notification)
- **Extends:** [ADR-0052](0052-expire-tentative-holds.md) decision 7 (hold notices go to the assigned coordinator), [ADR-0015](0015-in-app-notifications.md)

## Context
SCRUM-43 AC4 and SCRUM-50 AC2 tell the coordinator who raised a venue request when Venue Staff approve or reject it, so `decide_booking_request` sent `venue_booking_approved` and `venue_booking_rejected` to `request.requested_by`. They were written before an event could be reassigned. Since SCRUM-87 and SCRUM-96 the Lead can move an event to another coordinator, and the one who raised the request loses access to it: their notice linked to an event they can no longer open, and the coordinator now responsible for the event never heard the outcome.

The hold notices already went to the event's assigned coordinator (ADR-0052 decision 7), and SCRUM-59's notices about flagged bookings do the same (in review, PR #152). The Product Owner decided on 31 Oct that the decision notices follow them (SCRUM-115). SCRUM-43 and SCRUM-50 stay Done against their own criteria; SCRUM-115 is the new requirement.

## Decision
1. **`decide_booking_request` tells `event.coordinator_id`,** the event's coordinator now, with the decision and any reason as the `detail`, as before (SCRUM-115 AC1). Without a reassignment that is still the coordinator who raised the request, so nothing changes for them.
2. **A coordinator reassigned away from the event gets no decision notice** (AC2).
3. **The hold notices are unchanged:** placed, expiry changed, expiring and expired already go to the event's current coordinator. Tests marked `scrum_115` guard them (AC3).
4. **`requested_by` stays on the request** as who raised it: it is the actor on the request's history entry and is not a recipient any more.

## Consequences
- Every coordinator-facing venue notice now follows the event's current coordinator.
- SCRUM-70's rejection-with-an-alternative notice can rely on this recipient.
- No migration and no screen change. The frontend's mock backend doesn't model notice recipients, so it is unchanged.

## Revisit when
- An event can be left with no coordinator while it still has open venue requests.
