# ADR-0020: Event Organisers see their client organisation's event requests, scoped by one condition

- **Status:** Accepted; the same scope decides who may answer a clarification request, in [ADR-0029](0029-clarification-requests.md)
- **Date:** 2026-09-26
- **Story:** SCRUM-7 See only my own organisation's events
- **Supersedes:** part of ADR-0012: an organiser sees only the requests they submitted

## Context
SCRUM-7's ACs say an Event Organiser's event list holds only their own client organisation's events (AC1), that another organisation's event asked for by its identifier is refused (AC2), and that two organisers of the same organisation both see that organisation's events (AC3). The story has no comments or links.

Until now the list and the detail view were scoped to the organiser who submitted the request (ADR-0012 read "whose organisation owns the event" that way until SCRUM-66 existed). SCRUM-66 now links an organiser's account to one client organisation and files each new request under it (ADR-0013). These are left open:

1. **What "refused" is.** A `403` or a `404`.
2. **An organiser with no organisation.** Accounts from before migration `0007` have `users.organisation_id` NULL until an internal user links them. Comparing their NULL with the requests' column would either match nothing or, written carelessly, match every unfiled request.
3. **Where the organisation comes from.** The access token carries only `sub` and `role` (ADR-0006); the organisation is on the user row.
4. **Requests with no organisation.** Requests submitted before migration `0007` have `event_requests.organisation_id` NULL.
5. **Drafts.** SCRUM-20 adds drafts, which should stay with the organiser who wrote them rather than be shown to the whole organisation.
6. **Names.** The routes are `list_my_requests` and `get_my_request`, and the services `list_event_requests_for_organiser` and `get_event_request_for_organiser`.

## Decision
- **The organiser's scope is their client organisation.** `GET /api/events/requests` lists every request filed under the caller's organisation, newest first, whoever in it submitted each one. `GET /api/events/requests/<reference>` opens any of them, with its coordinator and equipment lines as before.
- **Another organisation's request is `404` "Event request not found.",** the same answer as an unknown reference, as ADR-0012 already decided for "not yours": a `403` would confirm the reference exists, and a reference is not an access control (ADR-0004). This is how AC2's "access is refused" is met.
- **An organiser with no organisation gets `403 organiser_without_organisation`** on the list and the detail view, as on submit (ADR-0013), with the message "Your account is not linked to a client organisation yet.". It is not an empty list: an empty list would read as "your organisation has no events", when the real problem is the account, and an internal user can fix it.
- **The organisation is read from the account on every request,** not put in the token. Linking an account, or moving it to another organisation, takes effect at once rather than when the token expires, at the cost of one primary-key lookup per request.
- **Requests with no organisation are visible to nobody,** not even the organiser who submitted them, as ADR-0013 expected. There is no organisation they can be shown under, and showing them to their submitter would need a second rule beside the organisation one.
- **The scope is one SQL condition,** `_visible_to_organiser` in `events/services.py`, used by both the list and the detail lookup, so they can't disagree. The detail's ownership check moved from Python into the query. SCRUM-20 narrows this one condition so a draft is seen only by its author.
- **Names are unchanged.** `list_my_requests`, `get_my_request` and the `..._for_organiser` services keep their names: "my" is the caller's view, and renaming endpoints or public service functions would touch every caller and test for no change in behaviour.
- **Colleagues don't see who submitted a request.** The response shapes are unchanged, and they have never carried `organiser_id`; showing the submitter's name is left to a story that asks for it.

## Consequences
- Organisers of one organisation share one list; an organiser who moves organisation stops seeing the old one's requests, including their own, and starts seeing the new one's.
- The list and the detail view each cost one extra user lookup. Submit already did this.
- Pre-`0007` requests stay invisible to organisers until someone files them under an organisation; no story does that yet.
- Organisers whose accounts pre-date SCRUM-66 can't read any requests until linked, as they already couldn't submit.
- **Known risk, out of scope:** registration is public and organisation ids are sequential (ADR-0013), so anyone who registers as an organiser with a guessed `organisation_id` now sees that organisation's event requests, not just their own. Before this change the same registration let them submit under the organisation but read nothing of anyone else's. It is the same self-registration trust gap as SCRUM-88 (internal roles self-registering) and closes with it, when accounts are provisioned or approved by an internal user.
- Tests: `tests/events/test_organisation_event_visibility.py` (marker `scrum_7`) runs the services on SQLite so the filters are real SQL.

## Revisit when
- SCRUM-88 or SCRUM-65's provisioning question is decided: the organisation link must go through the same approval, which closes the risk above.
- SCRUM-20 lands: narrow `_visible_to_organiser` for drafts.
- SCRUM-55 or another story needs the organisation's name, or a request's submitter, shown to organisers.
- A story moves an organiser between organisations and wants their past requests to follow them.
- A story gives pre-`0007` requests an organisation.
