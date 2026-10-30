# ADR-0115: The coordinator records or removes the withdrawal cut-off on the registration form

- **Status:** Accepted. Sending only what changed, `null` to clear and the backend's message under the box follow ADR-0075 and ADR-0086. The input, the Remove box, the confirmation's wording, the history's wording and re-reading after a refused save are the team's defaults to review.
- **Date:** 2026-10-31
- **Story:** SCRUM-69 Enable registration for an event and set its capacity (AC6, AC7), with SCRUM-53 See and withdraw my registration (AC2, AC3)
- **Extends:** [ADR-0075](0075-planning-actions-on-the-event-page.md) (decision 4, the registration form), [ADR-0086](0086-optional-withdrawal-cut-off.md) (the cut-off)

## Context
SCRUM-69 AC6: "The assigned Event Coordinator can also record an optional withdrawal cut-off decided by the Event Organiser, which must be before the event starts (SCRUM-53)". AC7: "Changing capacity or the withdrawal cut-off records which user did so and when."

The backend has done both since ADR-0086: `PATCH /api/events/requests/<reference>/registration` takes `withdrawal_cut_off` (a date-time sets it, with no offset it is business time; `null` clears it; left out, it is kept), refuses one at or after the start with "The withdrawal cut-off must be before the event starts." on the field, answers it in business time, and writes a `field_changed` history entry with the caller. The web app's types and mock already carried it. The coordinator's registration form had no input for it, so AC6 could be done through the API but not on screen (ADR-0075 and ADR-0086, Consequences).

The ACs don't say how the form asks for a date-time, how a cut-off is removed, or how a saved one is shown. The form also starts from nothing: the event record doesn't carry the registration settings, so nothing is prefilled (ADR-0075 decision 4).

## Decision
1. **On the same card, saved with the same button.** "Withdrawal cut-off" sits under Capacity on the "Registration settings" card, and "Save registration" sends it in the same `PATCH` as the other settings (ADR-0086 decision 2). The card still shows only for a confirmed event (ADR-0075 decision 2), though the backend would take a cut-off earlier (ADR-0086 decision 6).
2. **A date-time box, typed in Singapore time.** A `datetime-local` input, hinted "In Singapore time, before the event starts. Leave empty to keep the current cut-off." What is typed is sent with Singapore's offset (`2026-10-04T17:45` becomes `2026-10-04T17:45:00+08:00`, `toBusinessTimeIso`), as the hold expiry and booking times are. The offset is written out so the coordinator's own time zone can never change the instant, and the backend compares instants (ADR-0086 decision 3). Minutes only: a cut-off to the second isn't something an organiser decides.
3. **Like the other fields, nothing is prefilled, and only a change is sent.** An empty box sends nothing, so the event keeps its cut-off. Typing one sends it.
4. **"Remove the cut-off" is a tick box, and it sends `null`.** Emptying the box can't mean "remove", because an empty box already means "keep" (decision 3). So a separate "Remove the cut-off" box, saved with the button, sends `withdrawal_cut_off: null` (ADR-0086's *Revisit when*). While it is ticked, the date-time box is disabled and anything still in it is not sent. Ticking it is enough to enable Save; unticking it, with nothing else changed, disables Save again.
5. **The backend's rules and words, under the box they are about.** The form doesn't check the cut-off against the start, or against now: a cut-off already past is accepted by the backend (ADR-0086 decision 3, a default to review), and the form allows it too. A refusal on `withdrawal_cut_off` shows under the cut-off box; one on `registration_capacity` under Capacity, including the backend asking for a capacity when only a cut-off is sent to an event whose organiser asked for registration and that has none (ADR-0086 decision 6). After a refusal the form moves to the first refused box (`useFocusFirstError`), as the other long forms do.
6. **After saving, the card says when withdrawals close, from the backend's reply.** "Withdrawal cut-off: 4 Oct, 5:45 pm." or "No withdrawal cut-off: withdrawals close when the event starts.", after the open or closed and the capacity sentences (ADR-0075 decision 4). The date-time is shown in Singapore time in the page's usual short form, without the year, like the hold expiry.
7. **The history names the change in words and the value as a date and time (AC7).** The `field_changed` entry reads "Withdrawal cut-off changed", with Before and After as "4 Oct, 5:45 pm" in Singapore time, or "Not set". It already showed who made the change and when; before this it read "Withdrawal cut off changed" with the raw ISO value.
8. **Saved or refused, the record and its history are read again** (`onSettled`), as the decision and edit forms do: a refusal may mean the event has moved on, such as out of Confirmed.

## Consequences
- SCRUM-69 AC6 can be done on screen: record, see the refusal for one at or after the start, and remove. AC7 shows in the event's history on the coordinator's page.
- With a cut-off set on screen, SCRUM-53 AC2 and AC3's cut-off case can run end to end in the web app against the real backend: the attendee's page and refusal read `withdrawals_close_at` and `details.withdrawal_closed_at` from the backend (ADR-0083, ADR-0109). In mock mode the two don't meet: the registration mock and the withdraw mock keep separate data (`MOCK_WITHDRAWAL_CUT_OFFS`, ADR-0086 decision 9).
- **The form still can't show the saved cut-off when the page opens**, for the reason ADR-0075 gives for the capacity: the event record doesn't carry the settings. A coordinator who reopens the page sees an empty box and an unticked Remove; saving nothing about the cut-off keeps it. The ticket ADR-0075 lists (add the settings to the event record, then start the form from them) now covers `withdrawal_cut_off` too.
- No request shape changed, so the integration tests in `planning.int.test.ts` (which already record, keep, refuse and clear a cut-off) and the mock stay as they are.
- Tests: `RecordActions.test.tsx` ("the withdrawal cut-off (AC6, AC7)"), `eventHistory.test.ts`, and the journey in `e2e/planningActions.spec.ts`.

## Revisit when
- The event record carries the registration settings: start the box from the saved cut-off, and let emptying it mean "remove".
- The Product Owner rules on a cut-off already in the past (ADR-0086 decision 3): the form would then show the backend's new refusal with no change.
- The customer wants the year shown with the cut-off.
