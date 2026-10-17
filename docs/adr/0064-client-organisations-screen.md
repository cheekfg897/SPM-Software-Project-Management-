# ADR-0064: Staff record and list client organisations on one page; sign-up keeps its typed organisation ID

- **Status:** Accepted; the choices in decision 6 are defaults to review with the team
- **Date:** 2026-10-17
- **Story:** SCRUM-66 Record client organisations and link Organisers to them (AC1, AC5)
- **Extends:** ADR-0013

## Context
ADR-0013 gave the backend `POST /api/organisations` and `GET /api/organisations`, for internal
roles only, and made an Event Organiser name their organisation's ID at sign-up. The web app had
no screen for either route, so the only way to record an organisation was the API, and staff had
nowhere to look up the ID an organiser needs. The ACs say what an organisation records and who
must not see it (AC5: not Attendees), not how staff reach it or what the screen shows.

## Decision
1. **One page, `/staff/organisations`, for every staff role.** It lists the organisations and has
   a form to record one. The route allows `INTERNAL_ROLES`, the same set as the backend's
   decorators, so no staff role is offered a page the backend would refuse, and Attendees and
   Event Organisers are sent to their own home without asking the backend anything (AC5).
2. **A header link, "Clients", for staff.** Staff home is being reworked elsewhere, so the page
   is reached from the main navigation instead. "Organisations" was tried first, but with the
   bell and Log out it pushed the header 36px past a 320px phone; "Clients" fits, and an e2e
   test checks it.
3. **The list shows what the backend sends, in its order (by name):** ID, name, contact name,
   email and phone. The ID comes first because it is what an organiser signs up with. A missing
   phone reads "Not given". There is no paging, sorting or searching; the backend offers none.
4. **After recording, the form clears and says the new ID** ("Recorded Bayfront Partners. Its
   organisation ID is 4: give it to the organisation's Event Organisers so they can sign up."),
   and the list is read again. Every refusal is the backend's: per-field messages under the
   fields and the `409` duplicate-name message above the form.
5. **Organiser sign-up is unchanged.** Listing organisations needs a staff token, so a visitor
   cannot be offered a list to pick from, and AC5 keeps organisation details from Attendees.
   Sign-up keeps its typed organisation ID with the hint "ConnectSphere staff give you this when
   they add your organisation." A picker would need a new public route that exposes only names
   and ids, which is a backend decision (Tickets to open).
6. **Defaults to review (not agreed with the team).**
   - Every staff role sees the page and the header link, as the backend allows; the team may want
     it for the Event Coordinator Lead or coordinators only.
   - The page lives under `/staff/` and is reached from the header, not staff home, through a
     link labelled "Clients".
   - The confirmation tells staff to pass the ID on; ConnectSphere sends nothing to the
     organisation itself.
   - "Not given" for a missing phone.

## Consequences
- The mock backend (`mocks/handlers/organisations.ts`) answers both routes: staff only, by name,
  each field refused with `CreateClientOrganisationSchema`'s own message, names trimmed and
  unique exactly as typed. Two known differences: its email check is looser than marshmallow's
  (one `@`, no spaces), and it sorts with `localeCompare`, where Postgres uses its collation.
- The mock starts with organisations 1 to 3, the ids mock sign-up accepts
  (`MOCK_ORGANISATION_IDS`); a test keeps the two in step. An organisation recorded in the mock
  is not accepted by mock sign-up, which still reads that list.
- The contract tests the auth suite left as `it.todo` "lands with SCRUM-66" are now real: they
  record an organisation as the staff account and sign an organiser up to it.

## Revisit when
- The team wants organisers to pick their organisation at sign-up: the backend then needs a
  public list of names and ids, and AC5 must allow it.
- Staff home gains a place for this page.
- Client Management grows (edit, deactivate, link an existing organiser), per ADR-0013.
