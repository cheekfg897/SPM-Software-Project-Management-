# ADR-0077: Technical Support record each equipment line's outcome on the event's Equipment page, and staff see it beside the line

- **Status:** Accepted; decisions 1 to 6 are defaults to review with the team
- **Date:** 2026-10-18
- **Story:** SCRUM-48 Record the outcome of an equipment review
- **Extends:** ADR-0040, ADR-0061, ADR-0065

## Context
The backend has had SCRUM-48's route since ADR-0040: `POST
/api/events/requests/<reference>/equipment/<line_id>/outcome`, Technical Support Staff only,
with `provided_quantity` (a whole number of at least 0) and an optional `note`. The status
follows from the quantity (`fulfilled`, `partially_fulfilled` or `unavailable`), and the
equipment list (`GET .../equipment`) already sends each line's outcome: the quantity provided,
the shortfall, the note, the reviewer's name and the time. The web app had no screen for it.

As written in Jira on 2026-10-15, the ACs are: AC1 ten microphones asked for and six available
needs a note and shows partially fulfilled with the shortfall and the note; AC2 all of it is
fulfilled, a note optional; AC3 nothing suitable needs a note giving the reason; AC4 the
coordinator is notified of every outcome recorded or revised, with the outcome and the note; AC5
the outcome, the note and the reviewer are visible to internal staff on the event record, and
the Event Organiser sees the outcome and the quantity provided but not the note or the reviewer;
AC6 an outcome can be revised; AC7 a revision after the Operational Safety Check needs a new
check; AC8 an outcome on a Rejected, Cancelled or Completed event is refused, naming the status.

The ACs leave open where Technical Support record the outcome, how the coordinator sees it, what
the statuses are called on screen, and what the screen does about the ACs the backend does not
serve yet.

## Decision
1. **On the event's Equipment page, not a new screen.** Technical Support already reach
   `/events/<reference>/equipment` from their queue on Staff home (SCRUM-38, ADR-0061), and the
   page lists the event's lines (SCRUM-37, ADR-0065). Each line gets a "Record outcome" button
   for Technical Support, "Revise outcome" once it has one (AC6). It opens a form below the
   table with "Quantity provided" and "Note for the coordinator", holding the current outcome
   when revising. Coordinators get no outcome controls.
2. **The screen sends what was typed and the backend decides.** A blank quantity or a blank note
   is not sent, so the backend says what is missing; the status is never sent (ADR-0040
   decision 2). The screen does not check that a note is needed or that the quantity is not
   above what was asked for: the backend's message shows under the field (AC1, AC3). Any other
   refusal shows as an alert in the form, which stays open.
3. **Every reader of the page sees the outcome beside the line,** in an "Outcome" column:
   "Not reviewed yet" until there is one, then "6 of 10 provided, short by 4" (the backend's
   shortfall), the note, and "Reviewed by Tariq Hassan, 6 Oct, 9:15 am", or only when for a
   reviewer whose account is gone, worded as the event record's decisions are (AC1, AC2, AC5).
   That wording now comes from one helper in `src/lib/attributed.ts`.
4. **The status words are named once, in the backend's words.** `EQUIPMENT_LINE_STATUS_LABELS`
   in `features/equipment/constants.ts`: `partially_fulfilled` is now "Partially fulfilled",
   replacing ADR-0065's "Partly fulfilled", as the ACs and the Safety Officer's screen say.
   `requested` stays "Awaiting Technical Support". The Safety Officer's screen (SCRUM-98) keeps
   its own map for now, with "Requested" for `requested`; it can import this one once both
   have merged.
5. **After a save, or a refusal, the event's equipment is read again,** as for the
   coordinator's changes (ADR-0065). The queue on Staff home is read again whenever it opens,
   so a line with an outcome leaves it (ADR-0040 decision 8) with nothing more to do here.
6. **The mock backend records outcomes as the backend does:** Technical Support only (403 for
   anyone else, 401 with no token); the body first (`provided_quantity` a whole number of at
   least 0, `note` text, no unknown fields), then the event (404, drafts hidden), then the line
   (404), then more than was asked for, then the missing note. The reviewer is the caller, and
   the time is a fixed moment (`MOCK_OUTCOME_RECORDED_AT`) so tests and journeys can name it.
   A second Technical Support account (id 60) shows the reviewer is whoever signed in.

Also:
- The integration tests check the route's refusals with the accounts CI has. The checks that
  need a Technical Support account run only when `INTEGRATION_TECH_SUPPORT_EMAIL` and
  `INTEGRATION_TECH_SUPPORT_PASSWORD` are set, as the Venue Staff checks do; CI makes that
  account (frontend.yml). Recording on a real line needs an event assigned by a Lead, so it
  waits as a todo with SCRUM-37's.

## Deferred, each with what it needs
- **AC4, the outcome and the note in the notification:** delivered by the backend since this
  was written (SCRUM-50, ADR-0055 decision 5): the `equipment_outcome_recorded` notice's
  `detail` now reads, for example, "Projector: partially fulfilled, 6 of 10 provided. Note:
  Only six in stock", and the notifications page already shows a notice's `detail` as sent, so
  nothing changes here. The mock backend still adds no notification when an outcome is
  recorded: its notifications cannot be added to by another handler yet.
- **AC5, the Event Organiser's view:** the organiser's record sends each line's status but not
  the quantity provided, and organisers may not read the equipment types the lines are named
  from (`GET /api/equipment/types` is internal only). The organiser's request page shows no
  equipment. Needs the backend to send the organiser each line's type name and quantity
  provided (ADR-0040 decision 9). *Delivered by
  [ADR-0098](0098-organiser-sees-their-equipment-without-internal-notes.md).*
- **AC5, "internal staff":** the Equipment page is open to the assigned coordinator and
  Technical Support, as its list route is. The Lead and Venue Staff do not see the note or the
  reviewer; the Safety Officer sees the outcome and the note on their own screen (SCRUM-97).
- **AC7, a new safety check after a revision:** not in the backend yet (ADR-0040 decision 11,
  SCRUM-97 and SCRUM-98). The event's status on its record will show it once it is.
- **AC8, refusing a closed event:** the backend still accepts an outcome in any non-draft
  status (ADR-0040 decision 12), so the mock does too. The list does not carry the event's
  status, so the buttons are not hidden (as ADR-0065 decision 2); once the backend refuses, its
  message naming the status shows in the form's alert with no change here.

## Consequences
- Technical Support work from one page per event: what was asked for, what is free, what is
  held and what they will provide.
- Until AC8 lands in the backend, Technical Support can record an outcome on a closed event
  from this page, as they can through the API.
- A test that names "Partly fulfilled" (the SCRUM-37 branch) changes to "Partially fulfilled".

## Revisit when
- The backend refuses outcomes on closed events, or sends the event's status with its lines:
  hide the buttons outside the statuses that accept an outcome.
- The backend sends the organiser the quantity provided: show it on the organiser's request.
- The Safety Officer's screen merges: share the status words with it.
