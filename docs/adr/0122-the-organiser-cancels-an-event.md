# ADR-0122: The Event Organiser cancels their event at once, with a reason, which releases its arrangements as a rejection during planning does

- **Status:** Accepted; who cancels, that it takes effect at once, the reason, the statuses, what is released and who is told, and the confirmation naming what is released and how many attendees are told are the Product Owner's (SCRUM-61 as written on 29-31 Oct); everything else below is a default to review
- **Date:** 2026-10-31
- **Story:** SCRUM-61 Cancel an event and release its arrangements (AC1-AC9)
- **Extends:** [ADR-0093](0093-reject-an-event-during-planning.md) (releasing an event's arrangements), [ADR-0103](0103-tell-venue-staff-of-released-bookings.md) (telling Venue Staff of a released booking), [ADR-0029](0029-clarification-requests.md) (any organiser of the organisation acts on its requests), [ADR-0109](0109-attendee-event-page.md) (a cancelled event's page is read-only), [ADR-0118](0118-withdraw-a-held-arrangement-and-change-arrangements-only-while-planning.md) (arrangements change only while the event is planned), [ADR-0015](0015-in-app-notifications.md), [ADR-0031](0031-end-to-end-journey-through-the-test-client.md)

## Context
SCRUM-61 was the coordinator's until 29 Oct. The Product Owner's decisions of 29 and 30 Oct made it the Event Organiser's: the briefing says the Organiser "may postpone or cancel the event", so cancelling takes effect at once with no approval step, and a coordinator never cancels (SCRUM-112 was dropped). When the business side can't run an event, the coordinator rejects it instead (SCRUM-31, SCRUM-49). The customer's FAQ: "When an event is cancelled, it is cancelled. You can only submit a new request if you want to initiate a similar event."

* **AC1:** from Submitted, Under Review, Awaiting Clarification, Approved, Safety Review or Confirmed, the Organiser cancels with a reason and confirms it can't be undone; the status becomes Cancelled at once and the assigned coordinator is notified.
* **AC2, AC6:** every venue booking and active tentative hold is released, and each venue shows available for that period again.
* **AC3:** reserved equipment returns to the available quantity.
* **AC4:** every registered Attendee is notified.
* **AC5:** a cancelled event can't be edited, have its equipment outcome recorded, its venue arrangements withdrawn, changed or cancelled, or be registered for. The story says these already only allow listed statuses.
* **AC7:** open equipment requests close and leave Technical Support's list.
* **AC8:** Venue Staff are notified for each approved booking or hold released, naming the event, the venue and the period.
* **AC9:** an API-level end-to-end journey (moved from SCRUM-63).

The story's "Already built" note says the release, the closing of equipment requests and the Venue Staff notice are SCRUM-49's (`_release_arrangements`, ADR-0093), for cancelling to reuse.

## Decision
### Who and when (agreed)
1. **Only an Event Organiser cancels.** `POST /api/events/requests/<reference>/cancel` is `@requires_role(Role.EVENT_ORGANISER)`; every other role gets 403. **Default to review:** *any* organiser of the event's client organisation may, as any of them may answer a clarification (ADR-0029) and every one of them sees the event (SCRUM-7 AC3). The alternative is the submitting organiser only.
2. **From Submitted to Confirmed** (`CANCELLABLE_STATUSES`). Any other status is a 409 `cancellation_not_allowed`: "Only an event between Submitted and Confirmed can be cancelled; this one is completed." (the status as the API names it). The organiser's own draft is refused that way too, "this one is draft"; a colleague's draft is a 404, as it is hidden from them (ADR-0024).
3. **At once, in one commit:** the `cancelled` status (already in `event_request_status`), an `event_cancelled` history entry with the organiser as its actor and `{"reason"}`, and the release. Nobody approves it.
4. **The reason is required** (`CancelEventSchema`): missing or `null` 400 "A reason is required to cancel the event."; blank "Must not be blank."; not text "Not a valid string."; any other field "Unknown field.". Trimmed, no length limit, as a rejection's (ADR-0093). The two reason-only bodies now share `_RequiredReasonSchema`.
5. **Order of checks. Default to review:** the organiser's organisation (403 if they have none), the reference (404 for another organisation's event, ADR-0012), the status, then the body, as rejecting during planning does.
6. **The confirmation is the web app's, not the API's. Default to review:** the body carries no "I confirm" flag; the page asks the second question. The alternative is a required `confirm: true`.

### What is released (agreed, reusing ADR-0093)
7. **`_release_arrangements`, unchanged in behaviour,** now takes an `actor_id` rather than a `coordinator_id`: arrangements that don't hold their venue are withdrawn, with a `venue_arrangement_withdrawn` entry naming the organiser; approved and held ones are Released with their booking or hold let go through `_free_venue`, the one way a booking or hold is freed (AC2, AC6); reservations are deleted, so the equipment is free (AC3). Open equipment requests close with the status, `EQUIPMENT_NOT_NEEDED_STATUSES`, which already held Cancelled (AC7).
8. **AC5 needed no code,** as the story says. `tests/events/test_cancelled_event_is_locked.py` cancels through the service and checks each refusal. Withdrawing, changing, cancelling one or cancelling all of a cancelled event's arrangements is refused by SCRUM-93's rule that they change only while the event is planned (`get_event_for_arrangement_change`, ADR-0118), with its message naming `cancelled`; raising a new request is refused because the event isn't Approved (SCRUM-42). Cancelling adds no gate of its own.

### Who is told (agreed, with defaults on the details)
9. **The assigned coordinator** gets an `event_cancelled` notice, "This event has been cancelled by its organiser.", with the reason as its detail (AC1). **Default to review:** with no coordinator yet (a submitted request in the Lead's queue), nobody is told and it is logged, as for an answered clarification.
10. **Every registered Attendee** gets the same `event_cancelled` notice (AC4), **without the reason. Default to review:** the organiser wrote it for the coordinator. One who withdrew isn't told. Their registrations are left as they are, since the event's status says it is off and their page opens read-only (ADR-0109); the alternative is withdrawing every place.
11. **Every Venue Staff user** gets a `venue_booking_released_by_cancellation` notice for each booking or hold released (AC8), "A venue booking or hold was released because its event was cancelled.", with the arrangement, the venue and the period as its detail, as for a rejection (ADR-0103). It is a kind of its own because a rejection's notice says the event was rejected during planning.
12. **Nobody else. Default to review:** not the Safety Officers (an event in Safety Review leaves their list), Technical Support (their requests close), the Lead, or the organisation's other organisers.
13. **Migration `0052_add_event_cancelled`** adds `event_cancelled` and `venue_booking_released_by_cancellation` to `notification_kind` and `event_cancelled` to `event_history_entry_kind`, outside the transaction as 0049 and 0051 do; its downgrade deletes their rows and rebuilds both types. It revises 0051, the head of the stack below. Other open pull requests also add migrations (SCRUM-70's 0051, which also revises 0050, SCRUM-62's 0050 and SCRUM-56's 0053); whichever merges later re-chains.

### The web app and the mock
14. **The action sits on the organiser's event page,** below the record's sections, from submitted to confirmed, and never on the coordinator's. "Cancel event" asks first: "This can't be undone. Its venue bookings and holds are released and its reserved equipment returned." and how many registered attendees are told, from the backend's registrant count; "Keep the event" closes it. **Default to review:** it names what kinds of thing are released, not each booking, so the page doesn't filter the arrangements itself. The reason is sent only when typed, so the backend's message shows under the box. The history shows "Event cancelled" with the reason.
15. **Not built: "Want to change the date instead?"** The Product Owner asked the confirmation to offer a change request, but change requests are SCRUM-56's, not built yet. The link is a follow-up for SCRUM-56.
16. **The mock** answers the route in the backend's order of checks, with its messages, writes the history entry, withdraws or releases the arrangements and frees the venue and equipment mocks' stores, as its rejection does. It raises no notifications, as no mock route does.

### Concurrency
17. **Each venue arrangement is read under its row lock; the event row isn't locked. Default to review for the event row:** releasing reads each arrangement again `FOR UPDATE` before withdrawing or releasing it, as the coordinator's own actions do (ADR-0118), so an approval Venue Staff save while the event is being cancelled is released with its booking rather than withdrawn as the Pending it was, and an arrangement retired meanwhile is left alone. This also covers a rejection during planning, which shares the release (SCRUM-49). The event row itself isn't locked, as rejecting during planning doesn't lock it, so a coordinator action, or an equipment reservation, committed between the organiser's read and commit could interleave. SCRUM-56's change requests lock the event row (ADR-0126); cancelling takes the same lock when it calls SCRUM-56's withdrawal on cancellation.

## Consequences
- An organiser can withdraw an event at any point before it runs, and every venue, hold and unit of equipment it held is free at once.
- Cancelled is final: the FAQ's way back is a new request, and every action on the event refuses it.
- Tests: `tests/events/test_cancel_event.py`, `test_cancel_event_attendees.py`, `test_cancel_event_routes.py`, `test_cancelled_event_is_locked.py`, `test_event_cancelled_migration.py`, `tests/registration/test_registered_attendee_ids.py`, `tests/notifications/test_event_cancelled_notification_kinds.py` and the journey `tests/e2e/test_cancel_event_journey.py` (marker `scrum_61`); in the web app `CancelEventForm.test.tsx`, `eventCancellation.test.ts` for the mock, the history wording, and `cancelEvent.int.test.ts` against the backend.

## Revisit when
- SCRUM-56 lands: close a Pending change request as Withdrawn on cancellation, and link "change the date instead" from the confirmation.
- SCRUM-57's row lock lands (decision 17).
- The team wants the reason given to Attendees, or their places withdrawn (decision 10).
- Only the submitting organiser should cancel (decision 1).
- SCRUM-62 (draft PR #166) lands: its AC3 also tells Attendees of a cancelled event, through `notify_users_after_commit`. The Attendee notice here should then be sent through that helper, keeping one `event_cancelled` notice per Attendee (decision 10).
