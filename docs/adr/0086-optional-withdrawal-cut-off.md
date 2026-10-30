# ADR-0086: An optional withdrawal cut-off, recorded by the coordinator with the registration settings

- **Status:** Accepted; allowing a cut-off already in the past, and checking only a cut-off that is sent, are defaults to review
- **Date:** 2026-10-19
- **Story:** SCRUM-69 Enable registration for an event and set its capacity (AC6, AC7), with SCRUM-53 See and withdraw my registration (AC2-AC4)

## Context
On 19 Oct the Product Owner settled SCRUM-53's "Organiser's withdrawal cut-off", which [ADR-0032](0032-event-catalogue-contract.md) had left closing withdrawals at the event's start as a default:

- SCRUM-69 AC6: "The assigned Event Coordinator can also record an optional withdrawal cut-off decided by the Event Organiser, which must be before the event starts (SCRUM-53)". AC7: changing it records which user did so and when.
- SCRUM-53 AC2-AC4: an attendee can withdraw until the cut-off; it is optional, recorded with the event's registration settings, and with none set withdrawals close when the event starts; a withdrawal after it is refused, and the message shows when withdrawals closed.

The customer's rule behind it: "Organisers have discretion over registration/withdrawal conditions" (Week 2, A15), and every change after submission goes through the coordinator (Week 4 A43, Week 9 A11), the same as the capacity ([ADR-0043](0043-registration-settings-set-by-the-assigned-coordinator.md), A74).

The ACs leave open the cut-off's form (an instant or a lead time before the start), whether it may already have passed, and what happens when the event later moves earlier than it.

## Decision
1. **The cut-off is an instant, `withdrawal_cut_off`, a nullable column on `event_requests`** next to the other registration settings (migration 0042). AC6 says "a cut-off ... before the event starts", an instant rather than a lead time, and SCRUM-53's refusal shows "when withdrawals closed", which an instant answers directly. It is stored in UTC like every other instant (ADR-0009). Existing events have none.
2. **It is set through the registration settings route, by the same people.** `PATCH /api/events/requests/<reference>/registration` takes `withdrawal_cut_off` beside `registration_enabled` and `registration_capacity`, for the event's assigned coordinator only (ADR-0043 decision 1). Like the others, only what is sent changes:
   - an ISO 8601 date-time sets it; with no offset it is business time, as the event's own times and the catalogue's `starts_from` are (ADR-0009);
   - `null` clears it, so withdrawals close at the start again;
   - left out, it is kept;
   - anything that isn't a date-time (a word, a number, a boolean, an impossible hour) is `400` with marshmallow's `Not a valid datetime.` on `withdrawal_cut_off`.
3. **It must be before the event starts.** A cut-off at or after the start is `400`, `{"withdrawal_cut_off": ["The withdrawal cut-off must be before the event starts."]}`; the instants are compared, whatever offset was sent. One a moment before the start is accepted. *Default to review:* one already in the past is accepted too, so an organiser can close withdrawals now.
4. **Only a cut-off that is sent is checked against the start.** *Default to review:* if the event later moves earlier than a saved cut-off (a coordinator's edit, SCRUM-33), a change to the capacity or to opening registration still goes through, and the cut-off stays saved.
5. **Withdrawals close at the cut-off, or at the start, whichever is earlier.** `_withdrawal_closes_at` reads the cut-off through the event's heading (`list_event_headings`, the events module's public service) and answers the start when there is none or when it falls after the start (decision 4). So the existing `409 withdrawal_closed` refusal and its `details.withdrawal_closed_at`, in business time (ADR-0032), carry the cut-off with no other change (SCRUM-53 AC4). Registering is not affected: the cut-off closes withdrawals only.
6. **The cut-off has no status rule of its own.** Like a capacity, it can be recorded while registration is off and before the event is Confirmed; the status rule (ADR-0043 decision 4) is about enabling registration. A call with only a cut-off follows ADR-0043 decision 3 like any other: on an event that never had a capacity and whose organiser asked for registration, it is asked for a capacity unless it sends `registration_enabled: false`.
7. **A change is a `field_changed` history entry** (ADR-0025, ADR-0043 decision 7), with the caller and the previous and new value in business time, e.g. `"2026-10-14T18:00:00+08:00"`, or `null` when it is cleared (SCRUM-69 AC7). The route's answer adds `withdrawal_cut_off`, in business time or `null`.
8. **No database rule for "before the start".** The start is a date and a time held in business time in two columns, so a check constraint would have to rebuild the instant in SQL; the service is the only writer, so the rule lives there.
9. **The frontend's contract.** The registration mock (`mocks/handlers/eventPlanning.ts`, `eventPlanningRules.ts`) takes `withdrawal_cut_off` with the backend's checks, messages and history entries, and answers it in business time. The withdraw mock (`mocks/handlers/catalogue.ts`, from SCRUM-53's screen) closes at the earlier of the cut-off and the start, with the cut-offs as mock-only data in `MOCK_WITHDRAWAL_CUT_OFFS`, since the catalogue doesn't send them. The screen reads `details.withdrawal_closed_at` from the refusal rather than working the time out, so it shows the cut-off with no change of its own.

## Consequences
- SCRUM-53 AC2-AC4 are met by the backend. The coordinator's registration form on the event page has no cut-off input yet, so SCRUM-69 AC6 can be done through the API but not yet on screen; that is a follow-up (see the pull request's *Tickets to open*). *(The form gained the input with [ADR-0115](0115-withdrawal-cut-off-on-the-registration-form.md).)*
- `EventHeading` gains `withdrawal_cut_off`, so every reader of `list_event_headings` gets it; the attendee's own list doesn't show it (no AC asks).
- The migration adds one nullable column; downgrading drops it with any cut-offs recorded since.
- Tests: `tests/events/test_registration_settings.py` (AC6 and AC7 sections), `test_registration_settings_routes.py`, `test_withdrawal_cut_off_migration.py` (marker `scrum_69`), and `tests/registration/test_withdraw_registration.py` (marker `scrum_53`).

## Revisit when
- The Product Owner rules on a cut-off already in the past, or on an event moved earlier than its cut-off (decisions 3 and 4).
- ~~The coordinator's registration form gains the cut-off input: it should send `null` to clear it.~~ Done by [ADR-0115](0115-withdrawal-cut-off-on-the-registration-form.md): "Remove the cut-off" sends `null`.
