# ADR-0089: Technical Support take units out of service on the equipment type's page, and a reservation left short is marked on the event's Equipment page

- **Status:** Accepted; decisions 1 to 6 are defaults to review with the team
- **Date:** 2026-10-19
- **Story:** SCRUM-47 Take damaged equipment out of circulation
- **Extends:** ADR-0046, ADR-0065, ADR-0066

## Context
SCRUM-47's backend is on main (ADR-0046): `POST /api/equipment/types/<id>/out-of-service` takes
`quantity` units out as `damaged` or `under_maintenance`, `GET` on the same path lists the
entries still out with who recorded them and when, and `POST
/api/equipment/out-of-service/<id>/return` puts an entry's units back, recording who and when.
All three are for Technical Support Staff only. Availability leaves units out of service out,
and a coming reservation they leave short carries `needs_attention`. The web app had no screen
for any of it (ADR-0066 decision 8 left it out).

As written in Jira on 2026-10-19, the ACs are: AC1 an item's status can be set to Available,
Damaged or Under Maintenance; AC2 items that are not Available are left out of availability;
AC3 reservations depending on them are flagged and the coordinator is notified; AC4 the change
records the user and the time; AC5 a flagged reservation on an event past its safety check needs
a new check. AC2's arithmetic, AC3's notice and AC5 happen in the backend.

The ACs don't say where Technical Support do this, what the page shows of the units out, or
how a flagged reservation looks.

## Decision
1. **On the equipment type's own page** (`/staff/equipment/<id>`), in an "Out of service"
   section under the type's details, because units are taken out of a type, not of an event.
   Only Technical Support see it: the backend lists the entries to nobody else, so the page
   doesn't ask for them for anyone else either.
2. **The section shows three counts:** "In service" (as "7 of 10"), "Damaged" and "Under
   maintenance". The backend sends the entries, not the counts, so the page adds up the
   quantities of the entries it was sent and takes them from the type's total held. *Default to
   review:* this is the one place the page counts for itself; if the backend sends the counts,
   show those instead (see "Tickets to open").
3. **Each batch still out is a row**: its quantity, its reason in the ACs' words ("Damaged",
   "Under maintenance"), and "Recorded by <name>, <date and time>" (AC4). A batch whose recorder's
   account is gone shows only when.
4. **Putting units back ("Available", AC1) is one button per batch**, "Back in service", with
   no question first: taking them out again undoes it. The whole batch goes back, as the backend
   has it (ADR-0046 decision 2). Once it is back, a line says how many went back, by whom and
   when (AC4), from the backend's answer.
5. **Taking units out is a form under the list**: Quantity and Reason (a choice of Damaged or
   Under maintenance). A blank field is left out of what is sent, so the backend's "Missing data
   for required field." shows under it; "Only N units are in service." shows under the quantity.
   The form checks nothing itself (`frontend/CLAUDE.md`).
6. **A flagged reservation is marked in an "Attention" column** on the event's Equipment page,
   in words ("Needs attention: units of this type have gone out of service.", or "Not needed"),
   and a line above the list says some reserved equipment is short. The column sits after "When"
   and before SCRUM-85's preparation columns. The table scrolls sideways on a phone, so the line
   above it is what shows the shortfall without scrolling. Technical Support and the event's
   coordinator both see it, since both read that list (ADR-0037). That page is the only one in
   the web app that lists reservations.

Also:
- After units go out or come back, the type's list and every event's equipment (availability and
  reservations) are read again, since both change. A refusal reads them again too: "Only N units
  are in service." means someone else changed them meanwhile.
- The mock backend answers the three routes as the backend does, takes units out of service off
  what is available, and flags a reservation of a type with fewer units in service than are
  reserved. Every mock event shares one period, so the mock flags every reservation of that type
  and doesn't compare the period with today. When taking units out leaves a type short, every
  event reserving it loses its safety approval, as on the backend (AC5): its preparation is
  refused and a Confirmed event goes back to Approved. It doesn't send the coordinator's notice
  (AC3): no mock raises notifications yet.

## Consequences
- Other staff can't see how many units are out of service; they see the total held and, on an
  event's Equipment page, what is available.
- The counts are worked out in the page (decision 2), so they would be wrong if the backend
  listed only some of the entries; it lists all of them today.
- A coordinator may see a flag on a reservation that was not the one a broken unit was held for,
  as ADR-0046 says.

## Tickets to open
- Backend: send the counts in and out of service with the equipment type (to every internal role),
  so the page shows them rather than adding them up, and other staff see them too.
- Word the `safety_approval_withdrawn` history entry the backend writes for AC5 (and for SCRUM-33,
  SCRUM-48 and SCRUM-92): the event's history shows only "Safety approval withdrawn", without the
  equipment type or how many units went out.

## Revisit when
- The backend sends the counts, or lets other staff read the units out of service.
- Partial returns or a note on why units are out are added (ADR-0046's tickets).
