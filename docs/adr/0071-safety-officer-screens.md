# ADR-0071: The Safety Officer's home is their list, and each event's safety check is recorded on its card

- **Status:** Accepted; decisions 2, 5 and 6 are defaults to review with the Product Owner
- **Date:** 2026-10-18
- **Stories:** SCRUM-97 Submit an event for operational safety check (AC5, AC6); SCRUM-98 Record
  the operational safety check outcome (AC1-AC4, AC8); SCRUM-24 See the events my role is
  involved in (AC6, AC8, AC9, AC11)
- **Builds on:** ADR-0047 (the role, the list and the outcome route), ADR-0048 (no Planning
  status: planning happens while `approved`)

## Context
ADR-0047 delivered the backend: `GET /api/events/requests/awaiting-safety-review` and
`POST /api/events/requests/<reference>/safety-outcome`, both for Safety Officers only. Its "Still
owed" list names the frontend: a page for the list, and the outcome form. Until now a Safety
Officer who logged in landed on the placeholder Staff home, with no link and no page.

The ACs leave open where the Safety Officer works, how the form is laid out, what the outcomes
and checklist items are called on screen, and what the Safety Officer sees once an outcome is
recorded. One gap comes from the backend: the event record (`GET /api/events/requests/<ref>`) is
not open to the Safety Officer, so SCRUM-24 AC9 ("opening an event from the list shows the event
detail view") has nothing to open.

## Decision
1. **The list is the Safety Officer's home.** `/staff/safety-review`, open only to the Safety
   Officer (`RequireRole`; the backend's `403` stands behind it). They land there after logging
   in (`roleHome.ts`), and the header links to it as "Safety review", the same words as the
   status chip. The list keeps the backend's order (soonest first) and shows its empty-list
   message as sent.
2. **No detail page: everything is on the event's card.** The card shows what the list sends
   (SCRUM-97 AC6): the event's date and time, status, reference, expected attendance and
   accessibility needs; each booked venue's capacity, room layouts, facilities, accessibility
   features and booked period; each equipment request's quantity, notes and Technical Support's
   outcome. "Record safety check" opens the form on the same card. A detail page would need the
   event record, which the Safety Officer may not read (see Questions).
3. **Words come from the stories.** The buttons are SCRUM-98 AC1's "Approve", "Reject" and
   "Request changes". The seven checklist notes are labelled in AC2's words and order ("Expected
   attendance versus venue capacity", "Venue layout", "Emergency access", "Accessibility
   requirements", "Equipment placement", "Crowd movement", "Known venue restrictions"). The four
   items AC3 says the system holds no data for carry the hint "ConnectSphere holds no data on
   this. Record your own assessment." Technical Support's outcomes use the backend's
   `EquipmentLineStatus` names ("Fulfilled", "Partially fulfilled", "Unavailable", "Requested").
4. **The backend decides what is required.** The form sends every note as typed and the reason
   only when one was typed. The backend's messages appear under the note or the reason they are
   about, and focus moves to the first one; any other refusal (the two `409`s, a `404`) shows its
   message above the buttons. The reason's hint says it is required to reject or request
   changes (AC4), but the browser does not check it.
5. **After an outcome, the list is read again and a notice says what happened.** The event
   leaves the list because the backend no longer lists it. Above the list, a notice names the
   event and the outcome, shows the status the backend answered with (Safety review after an
   approval, Approved otherwise), says where the event goes next (it stays in Safety review
   until its coordinator confirms it; or it goes back to its coordinator at Approved, the
   planning stage), and that its coordinator has been notified (AC8). The notice reads TanStack
   Query's record of the outcome mutations (`useMutationState`), so it outlives the card.
6. **A refused outcome leaves the card as it is.** After a `409` the list is not read again, so
   the message stays where the Safety Officer can read it; reloading the page brings the list up
   to date.
7. **The contract tests make their own event in Safety Review.** CI now creates a Lead, Venue
   Staff and a Safety Officer next to the Event Coordinator (`frontend.yml`). The integration
   test walks an event to Safety Review (organiser submits, Lead assigns, coordinator approves,
   Venue Staff approve its venue, coordinator sends it), then lists it, records Request changes
   and Reject (each back to Approved), and Approve (off the list, a second outcome refused).
   Locally the checks that need those accounts skip without them, as SCRUM-43's do.

## Consequences
- A Safety Officer has a working page; the Staff home is no longer where they land.
- `SiteHeader`, `routes.tsx`, `config/routes.ts` and `roleHome.ts` each gained a few lines for
  the role.
- The mock (`src/mocks/handlers/safety.ts`) mirrors the backend's order, filters, status
  changes and every validation message; `src/integration/safety.int.test.ts` pins the real
  shapes, including the 15-field event the outcome answers with.
- The card reuses `formatSchedule` and `useFocusFirstError` from `features/eventRequests` and
  `LAYOUT_OPTIONS` from `features/booking`, as other features already do. They belong in
  `lib/` or `config/` once those features' open branches have merged.

## Questions for the Product Owner
- **Should the Safety Officer be able to open the full event record?** SCRUM-24 AC9 says opening
  an event from any role's list shows its detail view, but `GET /api/events/requests/<ref>` does
  not allow the Safety Officer, so the card shows only what the list sends. If yes, the backend
  route needs the role, and this screen can link each card to the record.
- Decisions 2, 5 and 6 above.

## Revisit when
- The Safety Officer is allowed to read the event record (decision 2).
- SCRUM-99 lands: flagged arrangements and reasons may need showing on the card.
- The notification kinds for Safety Review get messages and links (ADR-0047, "Still owed").
