# ADR-0067: The web app's venue catalogue screens: staff browse, Venue Staff edit

- **Status:** Accepted; the points marked *default to review* wait for the Product Owner
- **Date:** 2026-10-17; decision 7 changed 2026-10-19 for SCRUM-92's deactivation reason
- **Story:** SCRUM-25 Update venue catalogue (AC1 to AC6), SCRUM-67 Record setup and turnaround
  time for a venue (AC1, AC2, AC4, AC5)
- **Builds on:** ADR-0008 (opening hours), ADR-0011 and ADR-0033 (setup, turnaround and what a
  change reports), ADR-0053 (what a deactivation flags, and its category and note)

## Context
The backend has had the venue catalogue since Sprint 2: `GET /api/venues` (active venues, by
name), `GET /api/venues/<id>` (active or not), and, for Venue Staff only, `POST /api/venues`,
`PATCH /api/venues/<id>`, `POST /api/venues/<id>/deactivate` (with a category and a note since
SCRUM-92) and `/reactivate`. The web app had
no screen for any of them. The stories say what Venue Staff may do, not how the screens work, and
the API leaves these open for a client:

1. **Who gets the pages.** Reading is open to anyone signed in (SCRUM-25 AC4), but the stories
   are about staff: Venue Staff keep the records and Event Coordinators plan against them (AC3).
2. **How a list field is typed.** Facilities and accessibility features are lists of short text
   items that may not contain a comma.
3. **Opening hours on a new venue.** Left out, the backend opens the venue every day
   09:00 to 18:00; sent as `[]`, the venue is closed all week (ADR-0008).
4. **Blank fields on an edit.** A `PATCH` changes only the fields it is sent, so a field the user
   emptied and the client left out would keep its old value without a word.
5. **Where the overlap report goes.** A change to setup or turnaround time returns
   `overlap_warnings` and `block_overlap_warnings` (ADR-0033) in the `PATCH` response only.
6. **Deactivated venues.** `GET /api/venues` leaves them out, so a list built from it can't lead
   back to one to reactivate it (AC6).

## Decision
1. **Every staff role opens the venue list and a venue's page; only Venue Staff open the add and
   edit pages**, and only they see the Edit, Deactivate and Reactivate actions. The header gains a
   "Venues" link for every staff role. Organisers and Attendees get no venue pages: nothing in
   their stories needs one. *Default to review.*
2. **One item per line.** The two list fields are text boxes, one item per line; empty lines are
   dropped, and every other line is sent as typed. The backend trims, lower-cases and checks
   each item, and its messages for an item show under the box as "Item 2: …", counting the
   items sent, not the lines typed.
3. **A new venue's form starts with the standard hours filled in**, every day 09:00 to 18:00, and
   always sends `opening_hours`. Both forms then mean the same thing by no periods at all: closed
   all week. *Default to review.*
4. **An emptied required field is sent, so the backend refuses it** (AC2): an empty name or
   location as `""`, an empty capacity as `null`. Setup and turnaround times are the exception: a
   new venue sent without them takes the standard times (SCRUM-67 AC2), so the form says "Leave
   empty for the standard time" there, and an edit leaves out an emptied one, keeping the time
   the venue has.
5. **The overlap report shows on the edit page once the change is saved**, with each booking and
   block the backend named and the window they now share, and a link back to the venue. With no
   overlaps the page goes straight back to the venue.
6. **A deactivated venue's page still opens**, marked Deactivated, with a Reactivate button. The
   list only shows what `GET /api/venues` returns, so a deactivated venue is reached through its
   address, for example from the confirmation the page shows after deactivating it.
7. **Deactivating asks why first, and that question is the confirmation.** Since SCRUM-92 the
   backend needs a category and a note to deactivate (ADR-0053), and deactivating can't be undone
   by one click: every booking and request that hasn't ended is flagged "Needs Alternative
   Venue", a Confirmed event goes back to Approved and its coordinator is told, and reactivating
   clears the flags but leaves those events Approved. So "Deactivate venue" opens a question that
   says this, with the category (the five values in `src/config/unavailabilityCategories.ts`, none
   chosen to start) and the note, then Deactivate or Keep it active. Both go as chosen and typed,
   so the backend's messages show under their fields. Reactivating still takes one click. The
   wording and the categories' labels are a *default to review*.
8. **What the screens show is the backend's:** the list in its order, opening hours in its week
   order, and its messages. The only words of the web app's own are the empty list's ("No venues
   are listed yet."), because the backend sends a bare `[]`.

## Consequences
- The list and each venue's page are cached per venue and read again after any change to a venue,
  so the list and the page agree with the backend (AC3).
- The room layouts the backend accepts are in `src/config/venueLayouts.ts`, so a second feature
  can share them; the booking form still has its own copy.
- The overlap message for opening hours counts periods from 0 ("Overlaps opening period 0."),
  while the form numbers them from 1, so a message can name the period before the one it sits
  under.

## Revisit when
- Venue Staff need to find a deactivated venue without its link: the backend lists inactive
  venues for them (a ticket to open), and the list gains a filter.
- The backend's opening-hours messages number periods from 1.
- The Product Owner wants venue pages for Organisers.
- The booking feature's `UnavailabilityCategory` type (from SCRUM-92 on main) and
  `src/config/unavailabilityCategories.ts` meet: one should be built from the other.
