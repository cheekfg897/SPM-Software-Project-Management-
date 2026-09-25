# ADR-0017: The suitability check takes an event's requirements explicitly; the justification rule waits for booking requests

- **Status:** Accepted
- **Date:** 2026-09-25
- **Story:** SCRUM-36 Check whether a venue suits an event

## Context
SCRUM-36 asks for a venue to be checked against "a specific event": too small for the expected attendance (AC1), or missing a requirement such as step-free access (AC2), and reported suitable otherwise (AC3). AC4 adds that a coordinator who requests an unsuitable venue anyway must record a justification against the booking request.

Three things the story assumes don't exist yet:
1. An event request records only its `expected_attendance` in a structured way. Its venue and accessibility requirements are free text ("Step-free access and live captioning"). [ADR-0010](0010-search-prefill-deferred.md) already decided not to guess structured filters from that text; search (SCRUM-35) takes every filter explicitly instead.
2. No coordinator can read an event request through the API. Which coordinator may see which event is SCRUM-30 (assignment) and SCRUM-31 (review), neither built. A check that read any event for any coordinator would decide that access rule ahead of them.
3. Booking requests are SCRUM-42 (Sprint 3). There is nothing to record a justification against.

Options for what the check takes:
- **A. An event reference only.** The server reads the event. Capacity works; step-free access doesn't, because that requirement is prose the server would have to interpret — the guessing ADR-0010 refused. A sentence never matches a venue's items, so every event with any accessibility text would be "unsuitable" at every venue. It also makes the venue module read events and decide coordinator access.
- **B. The requirements themselves.** The client passes the event's expected attendance and the same layout, facility and accessibility items search takes. The same stance as ADR-0010.
- **C. Both.** Attendance from the event, items from the client. One answer from two sources, and the items still come from the client.

## Decision
- **Option B.** `POST /api/venues/<id>/suitability` (Event Coordinators and Venue Staff, the story's Roles field) takes `expected_attendance` plus search's `required_layout`, `required_facilities` and `required_accessibility`. The fields are validated and normalised by the same schema base (`_RequirementsSchema`) and matched by the same code (`_unmet_requirements`) as search, so the two can't drift apart.
- **What "suitable" means:** the venue's capacity is at least the expected attendance, it supports the required layout, and it offers every required facility and accessibility item (items trimmed and lower-cased on both sides, as SCRUM-35 does). Suitable if and only if nothing fails.
- **Response:** `{"suitable": bool, "reasons": [{"requirement": ..., "message": ...}]}`, always `200`: unsuitable is a result, not an error. `requirement` is one of `capacity`, `facilities`, `accessibility`, `layout`. Every failure is listed, capacity first, then facilities, accessibility and layout; each missing item is its own reason naming the item ("The venue does not offer step-free access.").
- **Not part of suitability:** whether the venue is free for the period (search, SCRUM-35; conflicts, SCRUM-44) and whether it is active (search hides deactivated venues; the check describes any venue by id, as `GET /api/venues/<id>` does). The event's free-text `accessibility_needs` and `venue_requirements` are not read; the coordinator reads them and passes the items.
- **AC4 is deferred to SCRUM-42.** The service function `check_venue_suitability(venue_id, requirements)` returns a `SuitabilityResult` with `suitable` and `reasons`. SCRUM-42 calls it with the event's expected attendance and the layout and accessibility requirements it records on the booking request, and refuses a request for a venue with `suitable == False` unless it carries a `justification`. SCRUM-58 (attendance changed after booking) can reuse the same call.

## Consequences
- SCRUM-36 can't be closed on this delivery alone: AC4 stays open until SCRUM-42 lands, as SCRUM-35's AC5 did under ADR-0010.
- No change to the events module, no cross-module call, no migration, and no coordinator access rule decided early.
- The client must send the event's values, as it already does for search; a wrong figure gives a wrong answer. Until SCRUM-30/31 give coordinators an event view, that figure comes from outside the API.
- Search and the check share `_RequirementsSchema` and `_unmet_requirements`; a new kind of requirement is added in one place and appears in both.

## Revisit when
- Event requests record structured requirements (ADR-0010's trigger). The check and search can then take an event reference, with access following SCRUM-30/31's assignment rule, and this ADR is superseded.
- SCRUM-42 lands: AC4 is delivered there against this function.
- The customer wants availability or active status folded into "suitable", or different reason wording.
