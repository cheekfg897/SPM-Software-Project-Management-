# ADR-0055: Venue Staff hear when a buffer change marks a booking Conflicting; an equipment outcome notice says what the outcome is

- **Status:** Accepted for the two notices; decisions 3, 4 and 6 are defaults to review with the team
- **Date:** 2026-10-18
- **Story:** SCRUM-50 Be notified about booking and equipment decisions

## Context

SCRUM-50 lists nine notification triggers. Most are already built by the story that owns the
decision, or are on an open pull request:

| AC | Trigger | Where it is built |
|---|---|---|
| 1 | Venue Staff, when a booking request is raised | `main`: `venue_booking_requested` (SCRUM-42, ADR-0035) |
| 2 | The coordinator, when a request is approved or rejected, with the reason | `main`: `venue_booking_approved` / `venue_booking_rejected` (SCRUM-43, ADR-0042) |
| 2 | ...or placed on hold, with its expiry | open PR for SCRUM-75: `venue_hold_placed`, `venue_hold_expiry_changed` |
| 3 | Technical Support, when equipment is requested | `main`: `equipment_requested` (SCRUM-37, ADR-0019) |
| 4 | The coordinator, each time an equipment outcome is recorded or revised | `main`: `equipment_outcome_recorded` (SCRUM-48, ADR-0040), without the outcome or the note |
| 5 | The organiser, when the event is confirmed | `main`: `event_confirmed` (SCRUM-49, ADR-0051) |
| 6 | Venue Staff, when a buffer change marks a booking Conflicting | nowhere |
| 7 | The coordinator, when a venue booked for their event becomes unavailable | open PR for SCRUM-92: `alternative_venue_needed` |
| 8 | The coordinator, 24 hours before a hold expires and when it expires | open PR for SCRUM-94: `venue_hold_expiring`, `venue_hold_expired` |
| 9 | The Safety Officer, on Safety Review; the coordinator, of the outcome with the reason | `main`: `safety_review_requested`, `safety_check_*` (SCRUM-97, SCRUM-98, ADR-0047) |

So this story builds two things: AC6, and the part of AC4 the notice is missing. The rest stay
with their own stories, so no notice is built twice. A comment on the ticket (17 Oct) proposes
cutting SCRUM-50 down to AC3 and AC6; it hasn't been applied, so the ACs above are the ones
built against.

## Decision

1. **A new `venue_booking_conflicting` notification kind (AC6).** When `update_venue` changes
   a venue's setup or turnaround time and marks confirmed bookings Conflicting (ADR-0045
   decision 10), every Venue Staff user is told about each booking it marks, after the
   change's own commit (ADR-0015). If the notices can't be saved, the change and the marks
   stay and a warning is logged, as for the other venue notices. Migration
   `0041_add_venue_booking_conflicting` (revision `0041_add_booking_conflicting`, because the
   full name is longer than `alembic_version`'s 32 characters) adds the value; its downgrade
   deletes those rows and rebuilds `notification_kind` with every value on `main`.
2. **Every Venue Staff user, as for a new request.** Venue Staff aren't assigned to venues
   (ADR-0035 decision 1, settled with the product owner), so nobody narrower can be picked.
   The staff member who made the change is told too: `update_venue` doesn't know who called
   it, and the notice is also the record of which bookings were hit.
3. **One notice per booking newly marked, naming the booking's event.** A notification
   belongs to an event (ADR-0015), so each booking gets its own, in start order, with the
   detail "`<venue>`: a change to its setup or turnaround time makes this event's booking
   overlap another booking or a block." A booking that was already Conflicting isn't
   reported again by a later change, so no change sends a duplicate for a booking Venue Staff
   have already been told about. *Default to review.*
4. **A booking with no event is marked but not reported.** `bookings.event_id` is nullable
   and not a foreign key (ADR-0045's model), and a notice must name an event, so a booking
   with no event, or with an event id that isn't saved, gets no notice. Every booking made by
   approving a request has its event. *Default to review.*
5. **The equipment outcome notice now carries the outcome and the note (AC4).** Its `detail`
   is "`<equipment>`: `<outcome>`, `<provided>` of `<requested>` provided.", followed by
   " Note: `<note>`" when the line has one, for example "Projector: partially fulfilled, 6 of
   10 provided. Note: Only six in stock". The outcome words are the status's, in plain
   English. A revision sends one more notice with the revised outcome, as it already did
   (ADR-0040 decision 6); a revision to fulfilled drops the note, as the line does.
6. **Notices for a withdrawn, changed or cancelled arrangement are not built.** ADR-0039 named
   SCRUM-50 as their owner, but SCRUM-50's ACs no longer list them. *Default to review*;
   listed in the pull request as a ticket to open if the team still wants them.

## Consequences

- Venue Staff learn about a buffer change's effect on bookings from their notifications, not
  only from the `PATCH` response the person who made the change sees.
- The frontend needs no change: it reads `kind` as a string and already shows `detail`.
- Four open pull requests (SCRUM-75, SCRUM-94, SCRUM-92 and this one) each add values to
  `notification_kind`, each with a downgrade that rebuilds the type from a list. Whichever
  merges later must re-point its `down_revision` and add the earlier one's values to its
  rebuild list.
- `_notify_about_booking` moved above `update_venue` in the venue services, unchanged, so the
  helper is defined before its first caller.

## Revisit when

- The team agrees or overturns decisions 3, 4 or 6.
- A story lets Venue Staff resolve a Conflicting booking (ADR-0045 decision 12): a booking
  cleared and then marked again would then be reported again.
