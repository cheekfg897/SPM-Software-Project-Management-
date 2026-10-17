# ADR-0052: Expire tentative holds with a scheduled command, and warn the coordinator first

- **Status:** Accepted; the warning lead time and the run interval are defaults pending the customer
- **Date:** 2026-10-18
- **Story:** SCRUM-94 Expire tentative holds automatically
- **Extends:** ADR-0045 (decisions 13 to 19, the hold), ADR-0015 (notifications)

## Context

SCRUM-75 (ADR-0045) lets Venue Staff hold a venue until an expiry they choose. A hold
stops counting the moment its expiry passes, because `_booking_is_live` ignores an
expired hold whenever bookings are read (ADR-0045 decision 17). Nothing marked the hold
Expired, though, and nothing told the coordinator. SCRUM-94 asks for both: the hold
becomes Expired with no user action, the coordinator is warned 24 hours before and told
when it expires, and an expired hold stays in the event's history with its expiry.

"With no user action" needs something to run on a clock. The app has no scheduler, no
worker and no deployed database yet: the repository's only secrets are the Telegram
ones `daily-standup.yml` uses.

## Decision

1. **The read-time rule stays the source of truth for the venue.** An expired hold frees
   the venue at its expiry instant whether or not anything has run (ADR-0045 decision
   17). What runs on a clock is only the bookkeeping: the Expired status, the history
   entry and the notices. A late or missed run therefore never double-books a venue.

2. **Two service functions do the work, and both take the instant to compare with.**
   `expire_holds(now=...)` moves every request On Hold whose expiry is at or before `now`
   to Expired. `send_hold_expiry_warnings(now=...)` warns about every hold On Hold that
   expires after `now` and no more than 24 hours after it. `now` defaults to the current
   instant; tests pass it, so the boundaries are pinned exactly. The expiry instant itself
   counts as expired, as in ADR-0045 decision 17, so a hold is warned about until its
   expiry and expired from it.

3. **Running either one again repeats nothing.** `expire_holds` reads only requests still
   On Hold, so an Expired one is never expired twice. A warning is recorded on the hold's
   booking (`bookings.hold_warning_sent_at`, migration 0037) in its own commit before the
   notice is sent, and only holds without one are warned. A notice that fails to save is
   logged and not retried, as for every other notice (ADR-0015).

4. **The request moves to a new status, `expired`; the hold's booking is left as it is.**
   The booking stays tentative with the expiry that passed, which `_booking_is_live`
   already ignores and which the history and the event's request list can show (SCRUM-94
   AC6). No `booking_status` value is added.

5. **An expired arrangement still counts until the coordinator withdraws it, like a
   rejected one.** It stays out of `RETIRED_REQUEST_STATUSES`, so it is still one of the
   event's active venues, and an event cannot reach confirmation past it (SCRUM-94 AC5):
   the Safety Review gate on the stack below SCRUM-49 (`list_unapproved_arrangements`,
   SCRUM-97) lists every active arrangement that is not approved, and an Expired one is
   not. It is added to the withdrawable
   statuses, so the coordinator can withdraw it and raise a new request for the venue
   (AC2). It is not decidable: an approval of it is refused with the usual "this one is
   expired".

6. **The expiry is recorded in the event's history** as a `venue_hold_expired` entry with
   no actor, because the system did it. Its details are the request, venue and booking ids
   and `expires_at` (ISO 8601 in UTC, as `venue_booking_requested`'s times are). The
   event's request list keeps showing an expired request's `hold_expires_at`.

7. **The notices go to the event's assigned coordinator.** SCRUM-94 AC3 says "the assigned
   Event Coordinator", and so does SCRUM-75 AC9. SCRUM-75's two notices (placed, expiry
   changed) went to whoever raised the request; after a reassignment that is the wrong
   person. All four hold notices now share one helper that reads the event's
   `coordinator_id` (added to `EventForBooking`). The two new kinds are
   `venue_hold_expiring` and `venue_hold_expired`, each with the expiry in business time
   as its detail, like SCRUM-75's.

8. **Changing the expiry moves the warning with it** (SCRUM-94 AC4). `change_hold_expiry`
   clears `hold_warning_sent_at`, so the next run warns again once the new expiry is
   within 24 hours. The coordinator is told about the change itself by SCRUM-75's
   `venue_hold_expiry_changed` notice, now sent to the assigned coordinator (decision 7).

9. **A CLI command runs both, and a scheduled workflow runs the command.**
   `flask expire-holds` (`app/modules/venue/commands.py`, registered like
   `create-staff-user`) expires first and warns second, so a hold that has already run
   out gets the expiry notice rather than a warning, and prints how many of each.
   `.github/workflows/expire-holds.yml` runs it at minute 7 of every hour, following
   `daily-standup.yml`: `schedule` plus `workflow_dispatch`, read-only token, the secret
   referenced by name. A `concurrency` group keeps two runs from overlapping.

10. **No database exists for the workflow to reach, so it skips cleanly.** Its first step
    checks the `DATABASE_URL` repository secret; when it is empty, the run prints a notice
    and every later step is skipped, so the run is green and does nothing. Once a deployed
    database exists, adding the secret switches it on with no code change.

11. **It goes live only after merge to `main`.** GitHub runs `schedule` and
    `workflow_dispatch` only from the default branch, so this branch cannot exercise the
    workflow itself; the command is tested through Flask's CLI runner and the venue
    booking journey instead.

### Defaults pending the customer

- **The 24-hour warning.** The customer gave no lead time, only that the coordinator is
  told before or when the hold expires. SCRUM-94 records 24 hours as the team's
  assumption, kept as `HOLD_WARNING_LEAD` in `venue/services.py`.
- **Hourly runs.** The Expired status and the notices can lag the expiry by up to an
  hour (the venue itself is free on time, decision 1). A shorter interval costs more
  Actions minutes on a private repository.

## Consequences

- No job is needed for correctness; the workflow can be paused or late without a venue
  being double-booked.
- The workflow runs every hour even with no database, taking a few seconds each time
  but billed as a minute. Disable it in the Actions tab if the minutes matter before a
  database exists.
- A coordinator warned about a hold and then given a later expiry is warned again near
  the new one. One whose hold is moved earlier, inside the window, is warned again too.
- The warning, once recorded, is not rolled back if its notice fails to save; that
  warning is lost rather than sent twice.
- The confirmation gates (SCRUM-97, SCRUM-49) live on another stack. Once both stacks
  merge, an expired arrangement keeps an event from Safety Review, and so from
  confirmation, until it is withdrawn, as a rejected one does; nothing here needs to
  change for that.

## Revisit when

- The customer gives a warning lead time, or wants the Expired status on time to the
  minute (a shorter interval, or a real scheduler with the deployment).
- The app is deployed: add the `DATABASE_URL` secret, or move the command into the
  deployment's own scheduler.
- A Pending request marked Conflicting by a hold should be cleared when the hold expires
  (ADR-0045 decision 19).
