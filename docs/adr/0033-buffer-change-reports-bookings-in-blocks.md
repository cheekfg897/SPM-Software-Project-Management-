# ADR-0033: A buffer change also reports confirmed bookings that now run into a block

- **Status:** Accepted
- **Date:** 2026-10-04
- **Story:** SCRUM-67 Record setup and turnaround time for a venue
- **Extends:** [ADR-0011](0011-venue-setup-and-turnaround.md): what a buffer change reports; [ADR-0016](0016-venue-block-warns-not-refuses.md): when a booking cuts into a block

## Context
Week 7 customer change #1 answered SCRUM-67's open question. Setup and turnaround time are set **per venue**, as ADR-0011 already assumed. The customer's example: a 10:00–12:00 event at a venue with 30 minutes' setup and 45 minutes' turnaround holds it 09:30–12:45. Bookings that become a problem must be identified, not silently removed. The default is still the team's call; ADR-0011's 30 minutes stands.

AC4 says that changing a venue's turnaround time leaves confirmed bookings valid, but *any* resulting overlap is reported to Venue Staff. ADR-0011 reports only pairs of confirmed bookings. A longer turnaround can also push a confirmed booking into a maintenance block. ADR-0016 already treats that pairing as a conflict when the block is created, so a buffer change that causes it went unreported.

## Decision
- When a `PATCH /api/venues/<id>` changes the setup or turnaround time, the response carries `block_overlap_warnings` next to `overlap_warnings`. Each entry is a confirmed booking whose padded period overlaps one of the venue's blocks: `booking_id`, `block_id`, and the overlapping window (`overlap_start`, `overlap_end`) in business time.
- Same rule as ADR-0016: the booking is padded by its venue's setup and turnaround, the block isn't (ADR-0011). A booking reported here is one that creating the block now would also report.
- Nothing changes the bookings or the blocks. Reporting is the only action, as for booking pairs.
- Every overlap that exists after the change is reported, not only new ones, as `overlap_warnings` already does.
- Tentative holds still aren't checked. They wait on SCRUM-75/94.

## Consequences
- `overlap_warnings` keeps its shape, so a client reading it is unaffected.
- The report is only in the response to the staff member who made the change; nothing is stored or sent to other Venue Staff.

## Revisit when
- SCRUM-44 (conflict detection) lands. It also takes on flagging bookings when *setup* time changes, and may want to store these reports or notify all Venue Staff.
- The customer wants blocks padded like bookings, or wants the requested event's setup and turnaround kept clear of blocks in search.
