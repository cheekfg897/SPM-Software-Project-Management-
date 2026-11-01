# ADR-0125: Who is told when a place is taken or given back, and when a replacement venue is approved

- **Status:** Proposed. Every decision below is the team's default to review; none was agreed with the Product Owner.
- **Date:** 2026-10-31
- **Story:** SCRUM-62 Be notified about changes, cancellations and registrations (AC4, AC5, AC6)
- **Extends:** [ADR-0015](0015-in-app-notifications.md) (who is relevant, notices after the commit), [ADR-0032](0032-event-catalogue-contract.md) (registering and withdrawing), [ADR-0108](0108-organiser-notice-locked-replacement-period-and-available-again-wording.md) (the replacement notice), [ADR-0109](0109-attendee-event-page.md) (where an Attendee's link opens)

## Context
SCRUM-62 has six criteria. Three are built here, because what triggers them is on `main`:

- **AC4:** "The Event Organiser is notified when an Attendee registers or withdraws where that affects available capacity."
- **AC5:** "The Attendee is notified when their own registration is confirmed or withdrawn."
- **AC6:** "Registered Attendees are notified when a replacement venue is approved for a confirmed event after its original venue became unavailable" (Week 7 change #2, through SCRUM-92).

The other three wait for their triggers. AC1 (the coordinator told when a change request is raised, the Organiser when it is decided) is SCRUM-56 AC5 and SCRUM-57 AC4. AC3 (Attendees told when an event is cancelled) is SCRUM-61 AC4. AC2 (Attendees told when an approved change alters date, time or venue) overlaps SCRUM-57 AC7, and the 29 Oct refinement asked for the overlap to be removed; it is left out until the Product Owner settles it.

The criteria leave five things open:

1. What "where that affects available capacity" excludes.
2. Which "Event Organiser" is told: the one who submitted the event, or every organiser of its client organisation (who all see its registrants, SCRUM-55).
3. What the notices say, and whether the Organiser's names the Attendee.
4. Whether AC6's Attendees are told only when the venue sent the event back from Confirmed, as the Organiser is (ADR-0108), or whenever a replacement is approved for an event they hold a place at.
5. How the notices are raised without failing the registration when they can't be saved.

## Decision
1. **Every registration and withdrawal tells the Organiser.** Each one takes or frees a place, so each changes the places available. A refused registration or withdrawal changes nothing and tells nobody. *Alternative:* only the ones that make the event full or free a place in a full one.
2. **The Organiser who submitted the event is told,** as for every other notice to an organiser (ADR-0028, ADR-0108). Other organisers of the organisation still see the registrants list. *Alternative:* every organiser of the client organisation.
3. **Four new kinds, each with its own message** (SCRUM-28: what a notice shows must match what happened):

   | Kind | To | Message | Detail |
   |---|---|---|---|
   | `registration_confirmed` | the Attendee | Your registration for this event is confirmed. | none |
   | `registration_withdrawn` | the Attendee | Your registration for this event has been withdrawn. | none |
   | `attendee_registered` | the Organiser | An Attendee registered for your event. | `99 of 100 places left.` |
   | `attendee_withdrawn` | the Organiser | An Attendee withdrew from your event. | `100 of 100 places left.` |

   The Organiser's notice doesn't name the Attendee: the places are what AC4 is about, and the registrants list (SCRUM-55) names them. Every notice links to `/events/<reference>`, which opens each role's own view of the event (ADR-0109). Migration 0050 adds the four values.
4. **AC6 tells every Attendee who still holds a place, whenever a replacement for a venue that became unavailable is approved.** It reuses `replacement_venue_approved` ("A replacement venue was approved for your event."), whose message fits them too, with its own detail: "Auditorium is no longer available for Partner Summit. Breakout room has been approved in its place." The Organiser's detail adds that the event still needs Safety Review and confirmation; the Attendee's leaves out the planning and the unavailability category (SCRUM-21). The Organiser is still told only when the venue sent the event back (ADR-0108). Attendees are told either way, because only a confirmed event takes registrations, so anyone holding a place is going to an event that was confirmed, and a change may already have sent it back to Approved with places held (ADR-0087) before the venue became unavailable. A replacement for an arrangement flagged only after a change (SCRUM-33) tells nobody, as ADR-0111 decision 3 has it for the Organiser: that is a change to the event, which is AC2's. *Alternative:* the Organiser's condition, so Attendees of an event a change had sent back hear nothing.
5. **`notify_users_after_commit` in `notifications.services` raises them.** The registration module tells people after the registration's own commit (ADR-0015); if the notices can't be saved, they are rolled back and `notification_failed reference=… kind=…` is logged on `connectsphere.notifications`, and the registration stands. The events module (`_raise_notifications`) and the venue module (`_notify_about_booking`) each keep their own copy of this with their own log line. Moving them onto the shared one changes log lines that about 17 tests, and any open PR's tests, assert on, so it is a follow-up.

## Consequences
- An Attendee hears of every registration they make or withdraw, and of a replacement venue for an event they are going to. The "You will be notified of any change" line on their event page (ADR-0109 decision 13) is true for a replacement venue; a date or time change waits for SCRUM-57.
- The Organiser of a popular event gets one notice per registration. That is AC4 as written; decision 1's alternative would cut it down.
- The registration module now calls the notifications module, and the venue module calls the registration module (imported inside the function, as it imports the events module, because the registration module imports the venue module's services).
- The web app shows a notice's message and detail as sent, so it needs no change for the new kinds. No response shape, error body or validation rule changes, so the mock backend doesn't either: the notifications mock serves only seeded notices, and no mock action raises one (ADR-0108, ADR-0111). `src/integration/registrationNotices.int.test.ts` checks the notices against the real backend.
- Migration 0050 revises 0049 (SCRUM-59, `venue_booking_reconfirmed`). Another open stack plans an 0050 too, and 0051 and 0052 add notification kinds as well, so whichever merges second is renumbered, re-chained and has its list of previous values extended. 0049's test now checks its notification kinds are a subset of the model's, as 0044's does, since a later migration adds more.

## Revisit when
- The Product Owner settles AC2 against SCRUM-57 AC7, or answers decision 1, 2 or 4 differently.
- SCRUM-61 (cancelling) and SCRUM-56/57 (change requests) land: AC3 and AC1 are raised there, and can reuse `notify_users_after_commit` and the registered-Attendee list (`_registered_attendee_ids`, made public then).
- The events and venue modules' copies of the after-commit helper move onto the shared one.
