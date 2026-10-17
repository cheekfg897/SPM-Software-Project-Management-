# ADR-0054: The equipment catalogue screens: a staff list, a page per type, and one form for adding and editing

- **Status:** Accepted; where the pages live, the header link, entering a venue by its number
  and the empty-list wording are defaults to review with the team
- **Date:** 2026-10-17
- **Story:** SCRUM-27 Maintain the equipment catalogue (AC1, AC2, AC3)
- **Extends:** ADR-0014

## Context
SCRUM-27's backend is on main: `POST` and `GET /api/equipment/types`, and `GET` and `PATCH
/api/equipment/types/<id>` (ADR-0014). As numbered in Jira on 2026-10-17:

- **AC1** "Can create and edit an equipment type recording name, description, total quantity
  held and the venue or store it is located at"
- **AC2** "Can view every equipment type with the total quantity of each"
- **AC3** "Only Technical Support Staff can create or change equipment records; other internal
  users can view them"

The web app had no screen for any of it. The ACs don't say where the screens live, how a
member of staff reaches them, or how "the venue or store" is entered. ADR-0014 records the
location as a `venue_id` or a free-text `store_name`, exactly one, and the responses carry the
venue's id, not its name. The venue screens and their mock are being built at the same time in
another branch, so this one can't rely on a venue list being there.

## Decision
1. **Four pages under `/staff/equipment`**:
   - `/staff/equipment`: every equipment type, in the backend's order (by name), with its
     description, total held and where it is kept (AC2). Every internal role may open it.
   - `/staff/equipment/<id>`: one type's page, the same details. Every internal role.
   - `/staff/equipment/new` and `/staff/equipment/<id>/edit`: the form (AC1). Technical Support
     Staff only.
2. **Only Technical Support see the "Add equipment type" and "Edit" links** (AC3). Anyone else
   who types the form's address is sent to their own home, as every role-only page does, and the
   backend refuses their request anyway (`403`).
3. **The header's "Equipment" link goes to the list**, for every internal role, since all of them
   may read it. *Default to review.*
4. **One form for adding and editing.** It has Name, Description, Total quantity held, and,
   under "Where it is kept", Venue number and Store name. Every field is sent every time:
   - an empty description is sent as `""`, which the backend stores as no description;
   - an empty quantity is sent as `null`, so the backend refuses it ("Field may not be null.")
     instead of an edit quietly keeping the old number;
   - an empty venue number or store name is sent as `null`, so filling in neither or both is
     refused by the backend with its own message on `venue_id` (ADR-0014). Moving equipment from
     a venue to a store is clearing one and filling in the other.

   The form checks nothing itself: the messages under each field are the backend's.
5. **A venue is entered and shown by its number** ("Venue 3"), because that is what the API
   holds and returns. *Default to review:* a venue picker, and showing venue names, wait for the
   venue screens (see "Revisit when").
6. **After saving, the type's own page opens**, read again from the backend, so what is shown
   is what was saved (stripped, with an empty description gone).
7. **An empty catalogue says "No equipment types yet."** The backend sends `[]` with no message
   for this list, so the wording is the web app's. *Default to review.*
8. **Taking units out of service (SCRUM-47) is not here**: its backend is still in review.

## Consequences
- The mock backend (`src/mocks/handlers/equipmentCatalogue.ts`) answers these four routes as the
  backend does: the roles, every field's messages, the location rules, the duplicate-name `409`
  and the `404`s. Its types 1 and 2 are the equipment mock's Projector and Microphone.
- The contract tests sign in as CI's Event Coordinator, so they check reading and refusals for
  real; adding and editing wait as `it.todo` until CI has a Technical Support account.
- The header gains a link for staff, which takes room on a small phone.

## Revisit when
- The venue screens land: pick the venue from a list and show its name instead of its number.
- SCRUM-47 lands: show the units out of service on a type's page.
- The backend sends a message for an empty catalogue: show that instead.
