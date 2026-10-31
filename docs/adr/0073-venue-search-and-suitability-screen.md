# ADR-0073: Coordinators search venues and check one venue's suitability from one web page

- **Status:** Accepted; the coordinator-only page, the optional end date and checking against
  the search's needs are defaults to review with the Product Owner; decision 9 (SCRUM-90 stays
  deferred) superseded by [ADR-0124](0124-venue-search-pre-filled-from-an-event.md), which opens
  this page from an event
- **Date:** 2026-10-18
- **Story:** SCRUM-35 Search and filter venues against event requirements, SCRUM-36 Check whether
  a venue suits an event
- **Builds on:** ADR-0010, ADR-0011, ADR-0017

## Context
Both stories' backends are on main: `POST /api/venues/search` (Event Coordinators only) and
`POST /api/venues/<id>/suitability` (Event Coordinators and Venue Staff). Neither had a screen,
so a coordinator could not use them. The ACs, the backend and the earlier ADRs leave a few things
open for the web app:

1. **Where the suitability check lives.** Search only returns venues that meet every requirement
   and are free, so checking a search result always says "suitable". SCRUM-36 matters when the
   coordinator has a venue in mind that the search did not return and wants to know why.
2. **What the check is measured against.** ADR-0017 makes the check take the event's expected
   attendance and requirements from the client, the same items search takes.
3. **The period.** SCRUM-35 AC1 says "date, start and end time". The backend takes any start
   and end instant, and events can run overnight (ADR-0002, `end_date`).
4. **Requirement items.** Facilities and accessibility are lists of free-text items, stored
   joined by commas, so an item can't contain a comma.
5. **Who gets the page.** Search is coordinator-only; the check also allows Venue Staff.
6. **SCRUM-35 AC5 / SCRUM-90** (open the search from an event, pre-filled). ADR-0010 deferred it
   because events record their requirements as free text, and SCRUM-90 is blocked on a story that
   records them in a structured way.

## Decision
1. **One page, "Find a venue"** (`/staff/venue-search`), for Event Coordinators. Its form is "what
   the event needs"; searching shows the venues that match, and a "Check a venue" section under
   the results checks any active venue (picked by name from `GET /api/venues`) against the same
   needs. The check is the way to find out why a venue is missing from the results.
2. **The check uses the search's needs.** Expected attendance is the search's minimum capacity,
   and the layout, facilities and accessibility are the same values. The page says the check
   covers capacity, layout, facilities and accessibility, not whether the venue is free (ADR-0017).
   A suitable venue reads "Suitable for this event"; an unsuitable one reads "Not suitable for
   this event" with each of the backend's reasons as it sent them.
3. **The period is a date, a start time, an end time and an optional end date** for an event that
   ends on a later day; left empty, the event ends on its start date. All are Singapore time and
   are sent with the `+08:00` offset. Whether the end is after the start is the backend's rule;
   its message shows under the end time.
4. **Facilities and accessibility needs are typed one per line.** Empty lines are dropped. The
   backend's messages for one item show under the box as "Item 2: ...", counting items, not
   lines.
5. **Every filter and the venue being checked live in the page URL**, as `frontend/CLAUDE.md`
   asks, so a shared link shows the same results and the same check. The search runs once the
   URL holds a filter; the results keep the backend's order (by name), and an empty result shows
   the backend's `message`.
6. **Each result shows** the venue's name, capacity, location, its id (the coordinator's venue
   request form asks for a venue ID, SCRUM-42) and each requested requirement it meets (AC3).
7. **Coordinators only.** Venue Staff may call the check, but this page is built around search,
   which they can't call. A check for Venue Staff (for example beside a booking request they are
   deciding) is a follow-up.
8. **Navigation:** the site header shows coordinators a "Find a venue" link.
9. **SCRUM-35 AC5 and SCRUM-90 stay deferred** under ADR-0010: no partial pre-fill from an event.
   SCRUM-36 AC4 (a justification when requesting an unsuitable venue) is already delivered by the
   venue request form (SCRUM-42), not by this page.

## Consequences
- A coordinator can shortlist free venues, see what each meets, and find out why a venue they
  expected is missing, without typing the needs twice.
- The page sends what the coordinator typed; a wrong attendance figure gives a wrong answer, as
  ADR-0017 already accepts.
- The room layout choices are shared with the venue request form through `src/config/`.

## Revisit when
- Events record structured requirements (ADR-0010's trigger): open this page from an event with
  its filters filled in (SCRUM-90), and check suitability per venue arrangement (SCRUM-93).
- Venue Staff need the check, or the Product Owner wants availability folded into "suitable".
