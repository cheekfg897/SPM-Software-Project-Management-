# ADR-0124: Venue search opens from an event with its date, times and attendance filled in

- **Status:** Accepted. Partial pre-fill, empty layout, facilities and accessibility, and the event's own words beside them are the Product Owner's (SCRUM-90, 19 Oct). Reading the event on the search page, searching only when asked, which fields carry over, leaving a value the event hasn't recorded empty, the link's place and wording, and the empty form after a refused read are the team's decisions (31 Oct). What the note says and the parameter's name are defaults to review.
- **Date:** 2026-10-31
- **Story:** SCRUM-90 Open venue search from an event with its filters pre-filled (split from SCRUM-35 AC5); SCRUM-113 records this decision
- **Supersedes:** [ADR-0010](0010-search-prefill-deferred.md), and [ADR-0073](0073-venue-search-and-suitability-screen.md) decision 9 (SCRUM-90 stays deferred)

## Context
ADR-0010 deferred opening venue search from an event because events record their venue, accessibility and equipment requirements as free text. It ruled out a partial pre-fill: filling in the times and attendance but not the requirements "would look complete when it isn't". ADR-0073 built the "Find a venue" page (`/staff/venue-search`) with every filter in the URL, and kept SCRUM-90 deferred on the same grounds.

On 19 Oct the Product Owner accepted a partial pre-fill and rewrote SCRUM-90's criteria:

1. The search can be opened from an event, with the filters that can be filled from the event's recorded details already populated.
2. The period comes from the event's proposed date, start and end time (and end date for overnight events), and the minimum capacity from its expected attendance.
3. Room layout, facilities and accessibility filters are left empty, because the event records those requirements as free text. The event's free-text venue and accessibility requirements are shown beside those filters, with a note that the coordinator must set them, so a partly filled search is never mistaken for a complete one.
4. The coordinator can change any pre-filled filter before searching.

The story no longer waits for structured requirements on event requests. The ACs leave open where the search is opened from, how the event's details reach the page, whether the search runs on arrival, and what to show for a requirement the event didn't record.

## Decision
1. **Partial pre-fill, as the Product Owner decided.** ADR-0010's "no partial pre-fill" is superseded. No backend change: `POST /api/venues/search` already takes every filter, and the event record already carries every detail used.
2. **The link names only the event.** The event's record, for its assigned coordinator, has a "Find a venue for this event" link first in its row of links (before "Venue requests" and "Equipment"). It opens `/staff/venue-search?for_event=<reference>`, with no filters in it. It shows in every status, as the other two links do.
3. **The search page reads the event from the backend.** With `for_event` in the URL and no filters yet, the page reads the event the way its record page does (`GET /api/events/requests/<reference>`, the same query) and fills the form in from it. The values come from the backend, not from a copy carried in the link, so a shared link shows the event as it is now. While it loads the page says "Loading the event…". If it can't be read (another coordinator's event is a `404`), the backend's message shows above an empty form, which still searches.
4. **Nothing is searched until the coordinator presses Search (AC4).** A search runs once the URL holds a filter (ADR-0073 decision 5), and the link puts none there, so the coordinator sees the pre-filled form with the empty filters before any results. Searching writes the filters into the URL beside `for_event`. From then on the form shows the URL's filters, not the event's, so Back and a shared link show what was searched.
5. **What is filled in (AC2).** Date from `proposed_date`; start and end times from `start_time` and `end_time`, to the minute; End date from `end_date` only when it is later than the start date (ADR-0073 decision 3 leaves it empty for a one-day event); Minimum capacity from `expected_attendance`. A detail the event hasn't recorded is left empty, not guessed (the readiness check's suggestion, 17 Oct). The fields are required, so the coordinator fills it in before searching. Location is not an event detail, so it stays empty.
6. **What is left empty, and what sits beside it (AC3).** Room layout, Facilities and Accessibility requirements are always empty when the form opens. Room layout moves into the row with the two requirement boxes, and a note headed "What \<event name\> asked for" sits just above those three. It says the date, times and minimum capacity come from the event and that room layout, facilities and accessibility do not, because the event records them as free text, so the coordinator sets them. It shows the event's "Venue requirements" and "Accessibility needs" as the organiser wrote them, or "None recorded", and leads back to the event. The note stays after searching, since the event's words are still what the coordinator is matching.
7. **A replacement search is unchanged.** SCRUM-92's replacement search still carries its filters in the link and searches on arrival (ADR-0088). It uses its own `event` parameter, which is separate from `for_event`.

## Consequences
- SCRUM-35 AC5 and SCRUM-90 are delivered in the web app alone. ADR-0010 is superseded, and ADR-0073 decision 9 with it.
- No request or response changed, so the mocks, `api.ts` and the integration tests stay as they are (`frontend/CLAUDE.md`, *Talking to the backend*).
- A shared link from before the search shows the event's current details. One from after it shows the filters that were searched.
- The search page now depends on the event-requests feature's hook and types to read the event. This follows the booking feature's use of the search's URL helpers.
- Tests: `features/venueSearch/eventFilters.test.ts`, `searchParams.test.ts` ("SCRUM-90 a search opened from an event"), `pages/VenueSearchPage.fromEvent.test.tsx`, `features/eventRequests/pages/EventRequestPage.test.tsx` ("SCRUM-90 event record"), and the journey in `e2e/venueSearch.spec.ts`.

## Revisit when
- Event requests record structured layout, facilities or accessibility requirements: fill those filters in too, and drop them from the note.
- The Product Owner wants the search to run on arrival, as the replacement search does, or wants the link shown only in some statuses.
- A result should lead straight to a venue request for the event the search was opened from.
