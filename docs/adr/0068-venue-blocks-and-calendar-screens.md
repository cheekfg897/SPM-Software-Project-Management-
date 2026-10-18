# ADR-0068: A venue's page shows its availability by day, and Venue Staff block it there

- **Status:** Accepted; the points marked *default to review* wait for the Product Owner
- **Date:** 2026-10-17
- **Story:** SCRUM-26 View a venue's availability calendar (AC1 to AC4), SCRUM-34 Block a venue
  for maintenance or internal use (AC1, AC2, AC4)
- **Builds on:** ADR-0067 (the venue screens), ADR-0009 (business time), ADR-0011 (setup and
  turnaround pad a booking), ADR-0016 (a block warns, it doesn't refuse)

## Context
The backend has `GET /api/venues/<id>/calendar?range_start=…&range_end=…` for every staff role,
and, for Venue Staff only, `GET` and `POST /api/venues/<id>/blocks` and
`DELETE /api/venues/<id>/blocks/<block_id>`. The calendar returns one flat list of unavailable
periods in time order; how much of a reason it gives depends on who asks (SCRUM-26 AC3). The
stories leave these open for the web app:

1. **Where the calendar lives**, and which range it opens on before anyone picks one.
2. **"For each day"** (SCRUM-26 AC1): the backend's list isn't split into days, and a period can
   run past midnight (a block over a weekend, or a booking padded into the next day).
3. **How a range is sent.** The API takes two instants; people pick days.
4. **Where a block's conflicts go** (SCRUM-34 AC2): `POST` saves the block and lists the
   confirmed bookings it cuts into, in its response only.
5. **Removing a block** (AC4): whether to ask first.

## Decision
1. **The calendar is a section of the venue's page**, for every staff role, so choosing a venue
   (AC1) is opening it from the venue list. It opens on the week from today (today and the six
   days after, in business time). The two days chosen are kept in the address (`?from=…&to=…`),
   so a shared link shows the same days. *Default to review.*
2. **Every day of the range is listed, each with the periods that touch it**, in the backend's
   order. A period that runs past midnight shows under each day it touches, with its full start
   and end; a day with none says "Nothing booked or blocked." This only arranges what the backend
   sent; nothing is filtered out of the range or re-sorted.
3. **The range is sent as whole days in business time:** `range_start` is the first day's
   midnight and `range_end` the midnight after the last day, both without an offset, which the
   backend reads as business time (ADR-0009). A last day before the first is the backend's to
   refuse; its message shows under the field it names.
4. **Each period shows its kind, its times and its reason as the backend words it.** A booking
   shows the period it holds the venue (padded by setup and turnaround, ADR-0011) and, beside it,
   the event's own times. Kinds are "Booked", "Tentative" and "Blocked".
5. **Venue Staff block the venue from the same page**, with a start, an end (date and time, in
   business time, sent without an offset), a category from the five the backend takes
   (UNAVAILABILITY_CATEGORIES, SCRUM-92 AC2, ADR-0053) and a reason, and see its blocks listed
   underneath with their category and a Remove button each. Other staff see neither: the blocks
   list is Venue Staff's only (ADR-0016), and they see blocks in the calendar as the backend
   words them.
6. **A block that cuts into confirmed bookings is still saved**, and the page then says which:
   each booking, its event, and the period it holds the venue (SCRUM-34 AC2). *Default to review:*
   the report stays until the next block is saved; it isn't stored anywhere.
7. **Removing a block asks for no confirmation.** It frees the period at once (AC4), and a block
   is quick to add again. *Default to review.*

## Consequences
- The calendar's query key holds the viewer's id, since the reasons depend on the role; signing in
  as someone else reads it again.
- Saving or removing a block reads the venue's blocks and its calendar again, so both show it.
- Each day's list is worked out in the browser from the backend's list (`calendarDays`); a long
  range makes a long page.

## Revisit when
- Staff want a month grid instead of a list of days, or the calendar on its own page across venues.
- The Product Owner wants a confirmation before a block is removed, or the conflict report kept.
- The backend splits the calendar into days itself.
