# ADR-0088: The coordinator sees why an arrangement needs an alternative venue, finds another venue for its period and raises the replacement from the Venue requests page

- **Status:** Accepted; never offering the venue being replaced follows the Product Owner's
  decision of 19 Oct; the wording, showing the reasons only while flagged, and the two-step
  replacement (choose in the search, send from the form) are defaults to review with the team;
  an arrangement flagged after a change to the event (SCRUM-33 AC6) is offered the same way in
  decision 8, a default until Venue Staff can reconfirm a booking (SCRUM-59)
- **Date:** 2026-10-19
- **Story:** SCRUM-92 Flag bookings affected when a venue becomes unavailable (AC1, AC4, AC6,
  AC7, AC8, AC9)
- **Extends:** ADR-0053, ADR-0069, ADR-0073, ADR-0094

## Context
The backend has flagged arrangements since ADR-0053: each listed arrangement carries
`needs_alternative_venue`, every block or deactivation that flagged it (`unavailability`: the
category, Venue Staff's note and the period, `ends_at` `null` for a deactivation) and
`replaces_request_id`. A replacement is an ordinary `POST .../booking-requests` with
`replaces_request_id`, allowed while the event is Approved or in Safety Review. The web app
showed only a bare "Needs an alternative venue" line (ADR-0069 decision 2) and had no way to
raise a replacement.

AC6 says the coordinator "can open venue search for the event's original period and raise a
replacement booking request linked to the flagged booking". It doesn't say where the search
starts from, what it is set to, or where the request is sent from. The other ACs say what must
be true, not how it reads.

## Decision
1. **Why it is flagged sits under the arrangement.** While the backend flags an arrangement, its
   item on the Venue requests page shows "Needs an alternative venue" and lists each cause in
   the backend's order: the category's label, the note, and the period in business time, e.g.
   "Maintenance: Roof repairs. Unavailable from 26 Nov, 8:00 am to 26 Nov, 6:00 pm." A
   deactivation, which has no end, is unavailable "until the venue is reactivated" (AC9). The
   arrangement's own details stay above it unchanged (AC4).
2. **The flag shows only while the backend sets it, whatever the arrangement's status.** A
   cleared flag (AC8) and a released arrangement (AC7) show no causes, though the backend keeps
   a released one's. The page reads only `needs_alternative_venue`, so an On Hold arrangement,
   which the Product Owner decided on 19 Oct is flagged too (AC1), shows its causes and "Find
   another venue" once the backend flags it. The status label "Released" and the rule that a
   retired arrangement offers no actions were already on the page (ADR-0069).
3. **"Find another venue" opens the existing Find a venue page** (ADR-0073), set from the
   flagged arrangement: its date, start and end times in business time, an end date when it
   ends on a later day, its expected occupancy as the minimum capacity and its layout. Facilities
   and accessibility are left empty: the arrangement doesn't carry them, and the event records
   its needs as free text (ADR-0010). The search runs straight away. The URL also names the
   event, the arrangement and its venue (`event`, `replaces`, `instead_of`), so the page knows
   it is finding a replacement, and for which venue.
4. **In a replacement search, each venue found offers "Request this venue".** It leads back to
   the event's Venue requests page with the request form filled in from the flagged arrangement
   (the venue chosen, its period, purpose, occupancy and layout) and marked "Replacing <purpose>",
   carried in the URL (`replaces`, `venue`). The coordinator checks it, changes what they need to,
   and sends it with `replaces_request_id`. The form rather than a one-click request on the search
   page, because the backend's per-field refusals (opening hours, a justification for an
   unsuitable venue) then show under their own fields, and the coordinator can add a
   justification. "Stop replacing" drops the replacement and leaves an ordinary form.
   **The venue being replaced is never offered:** its card, if the search lists it, says "This is
   the venue being replaced." instead. The Product Owner decided on 19 Oct that a replacement is
   always another venue for the original period; the same venue at another time is a change
   request (SCRUM-56, SCRUM-57). The form doesn't check a venue ID typed by hand: the backend
   will refuse the same venue in a later PR, and its message will show under the field.
5. **The backend decides whether a replacement is allowed.** "Find another venue" is offered on
   every flagged arrangement, whatever the event's status. A refusal shows in the form: the
   message (e.g. "Only an approved event or one in Safety Review can replace a venue; this one is
   confirmed.") above it, and a message about `replaces_request_id` (e.g. "This venue arrangement
   does not need an alternative venue.") in the "Replacing" note.
6. **The replacement is linked both ways on screen.** In the event's list it reads "Replaces
   <purpose>" (or "Replaces arrangement <id>" if the list doesn't hold the original). In Venue
   Staff's decisions queue, a replacement says it replaces a booking whose venue became
   unavailable and that approving it releases that booking (AC7).
7. **The mock backend checks a replacement as the backend does:** the 400s on
   `replaces_request_id` (not the event's, not flagged, not a whole number from 1), the 409 for an
   event neither Approved nor in Safety Review, and releasing the original when Venue Staff
   approve the replacement. One event in the mock is in Safety Review with an arrangement whose
   venue was deactivated.
8. **An arrangement flagged after a change to the event is offered another venue too**
   (SCRUM-33 AC6, ADR-0094; added 25 Oct when SCRUM-33's flags reached main). The backend's
   `_check_replaceable` accepts either flag, and until Venue Staff can reconfirm a booking
   (SCRUM-59), a replacement is the only way to clear a change flag. So while
   `flagged_after_change` is set, the same notice lists each of `reassessment_flags` as
   "Requires reconfirmation: …" or "No longer suitable: …" and offers "Find another venue". An
   arrangement flagged both ways shows both lists under one heading ("Needs an alternative
   venue") with one button. The mock accepts a replacement for either flag, and approving it
   releases the original so its change flag stops counting, keeping the reasons.

## Consequences
- The booking feature builds the search's URL with the venue search's own helpers
  (`replacementSearchPath`), and the venue search links back through
  `replacementRequestPath` in `config/routes.ts`, so neither feature imports the other's
  components.
- The booking mock still knows only venues 1 and 2 (`MOCK_BOOKING_VENUES`). In `dev:mock`,
  choosing another venue from the search is refused as "Venue not found.", as it already was for
  an ordinary request.
- The mock does not move the event in Safety Review back to Approved when a replacement is
  approved (ADR-0053 decision 13); its events are fixed data.

## Revisit when
- The backend refuses a same-venue replacement and flags On Hold arrangements (SCRUM-92's
  "Changed after review" note): mirror the refusal and the flag in the booking mock.
- The team decides the defaults in the status line.
- SCRUM-59 lets Venue Staff reconfirm a booking: decide whether a "Requires reconfirmation" flag
  still offers "Find another venue", or only waits for Venue Staff.
- SCRUM-90 gives events structured requirements: set the search's facilities and accessibility
  from them too.
