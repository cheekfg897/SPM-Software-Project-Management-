# ADR-0114: A timing or quantity change marks the event's equipment reservations, and Technical Support settle each by confirming it or recording the line's outcome

- **Status:** Accepted; showing a shortfall to Technical Support with no separate notice (AC2) and reopening unavailable and partially fulfilled lines on a timing change (AC12) are the Product Owner's answers of 27 Oct (answers 3 and 4); confirming to the event's period now, a reopened line keeping its reservation and building nothing past SCRUM-60's criteria were decided before the build; everything else below is a default to review, decisions 22 and 23 included (added in review of PR #154)
- **Date:** 2026-10-28
- **Story:** SCRUM-60 Reassess equipment reservations after a timing change (AC1-AC12)
- **Extends:** [ADR-0025](0025-event-edits-significant-changes-and-history.md) (Technical Support are told of a significant edit), [ADR-0037](0037-equipment-availability-and-reservation.md) (availability and reservations), [ADR-0040](0040-equipment-review-outcome.md) (the outcome), [ADR-0092](0092-equipment-line-changes-reopen-the-review.md) (a line change reopens the line), [ADR-0094](0094-reassess-each-venue-arrangement-after-a-significant-change.md) and [ADR-0107](0107-tell-the-safety-officer-of-changes-in-safety-review.md) (flags, the gates and Safety Review), [ADR-0102](0102-reserving-equipment-notifies-nobody.md) (one notice per review)
- **Supersedes:** [ADR-0092](0092-equipment-line-changes-reopen-the-review.md) decision 6's "Not built" (Technical Support had no way to shrink a reservation)

## Context
An equipment reservation copies the event's start and end when it is made (ADR-0037). Before this story a change to the event's date or time left every reservation held for the old period, and a lower line quantity left the full reservation in place (ADR-0092, answer 7 of 25 Oct). SCRUM-60 now says:

* **AC1:** any saved date or time change, by a direct edit (SCRUM-33) or an approved change request (SCRUM-57), marks every reservation for reassessment and tells Technical Support.
* **AC2:** a recheck for the new period shows any shortfall to Technical Support when they review; the coordinator hears through the outcome only.
* **AC3:** when the equipment is free, Technical Support confirm the reservation, which moves it, and the coordinator is told once; no outcome is recorded.
* **AC4:** otherwise they record a SCRUM-48 outcome: partially fulfilled keeps the free quantity for the new period and releases the rest; unavailable releases it.
* **AC5:** a marked reservation holds the event out of Safety Review and confirmation, and the refusal names it.
* **AC6:** until then it stays held for its old period and is back on Technical Support's awaiting-action list (SCRUM-38).
* **AC7:** attendance or the free-text equipment requirements mark nothing.
* **AC8, AC9:** a new line quantity marks the line's reservation; recording the reopened line's outcome is the confirmation and trims a reservation above a lowered line. A new reservation can never exceed its line.
* **AC10, AC11:** moving a reservation, or reporting it unavailable, needs a new safety check; preparation details move with it.
* **AC12 (27 Oct):** a date or time change reopens every line recorded unavailable or partially fulfilled, for a fresh outcome; until then it has no current outcome and holds the event back.

## Decision
### Marking
1. **A flag on the reservation.** `equipment_reservations.needs_reassessment`, a boolean that defaults to false (migration `0050_add_needs_reassessment`; its downgrade drops it). It sits beside SCRUM-47's `needs_attention`, which an out-of-service change recomputes for every coming reservation, so the two can't share a column. **Default to review:** a flag rather than a table of reasons as venues have (ADR-0094). The reason needs no row: the reservation's own period against the event's says whether the timing moved, and its quantity against the line's says whether the quantity did.
2. **One public entry point for a timing change: `events.services.reassess_equipment_after_timing_change(event_id, *, session)`.** It marks every reservation of the event, reopens every line recorded unavailable or partially fulfilled (AC12, keeping the outcome in the history as SCRUM-37 does), and sends an event in Safety Review back to Approved if it did either (SCRUM-33 AC9, as ADR-0107 reads a flagged arrangement). It doesn't commit. The direct edit calls it when a date or time field changed, in the edit's own commit. **For SCRUM-57:** an approved change request calls it in its own commit and then tells Technical Support, as the edit does through `_reassess_arrangements`.
3. **Technical Support are told by the notice they already get** for a significant edit to an event with equipment lines (`significant_change`, ADR-0025): one per edit, not one per reservation.
4. **A new quantity on a line marks that type's reservations** (AC8), through `equipment.services.mark_type_reservations_for_reassessment`, alongside SCRUM-37's reopening. A new equipment type still releases the old type's reservations (ADR-0092). New notes alone mark nothing.
5. **Decided before the build (default to review): a reopened line keeps its reservation**, held for the old period, until its fresh outcome moves, trims or releases it.

### What Technical Support see (AC2, AC6)
6. **Reassessed by equipment type.** An event has one line per type (ADR-0019) and reservations hold no line id, so a type's marked reservations are the line's and are reassessed together. `GET /api/equipment/events/<reference>/reassessments` (Technical Support for any event, the assigned coordinator for theirs) gives, per type by name: the marked reservations as the record shows them, each with the period it still holds; their total; the event's period now; what is free for it; and the shortfall.
7. **Default to review: the recheck is SCRUM-45's count, with the event's own marked reservations left out.** They are the units being reassessed, and the old period they still hold may overlap the new one. Any other reservation counts as taken, the event's own unmarked ones included.
8. **The awaiting-action list (SCRUM-38) lists a line whose reservation is marked**, whatever its outcome, and each entry gains `equipment_type_ids_to_reassess`. A reopened line is listed already, having no outcome.
9. **The shortfall is shown, not sent (AC2, answer 4).** Nobody is notified of it.

### Settling a marked reservation (AC3, AC4, AC8-AC12)
10. **Confirming: `POST /api/equipment/events/<reference>/reassessments/<equipment_type_id>/confirm`,** Technical Support only. It keeps the type's marked reservations' units, up to what the line's outcome provides, for the event's period now, and unmarks them. **Decided before the build: the period is the event's now,** so after several changes the latest wins. It is refused, in this order: 404 for a draft or unknown event; 409 `equipment_not_reservable` for a completed, cancelled or rejected one; 404 when the type has nothing marked; 409 when the line has no current outcome ("Record its outcome instead: that settles the reservation.", since a reopened line's outcome is its review, AC8, AC12; a type with no line is decision 22); 409 `reservation_cannot_move` when fewer are free than would be kept. **Default to review:** any status before the event is over may confirm, Confirmed included, since SCRUM-57 can mark a Confirmed event's reservations.
11. **Recording an outcome on a line whose reservations are marked settles them**: they keep the provided quantity, never more than they hold, oldest reservation first, the one that straddles trimmed and later ones deleted, so their units are free again. Unavailable releases them all (AC4); a lowered line's fulfilled outcome trims them to it (AC9). A reopened line's fresh outcome moves the reservation it kept, up to what it held; more units are a new reservation.
12. **Default to review: keeping more than is free is refused, with one message for both ways in:** "Projector: only 1 free for the event's period, not the 3 to keep. Record an outcome that provides no more than 1." (409 `reservation_cannot_move`), checked before anything changes.
13. **One notice per review (single-notification clarification).** An outcome sends SCRUM-48's notice. Confirming sends the coordinator one `equipment_outcome_recorded` notice whose detail says what was confirmed: "Projector: 3 reserved, confirmed for the event's new date and time." **Default to review:** reusing that kind, since confirming is the review; a new kind would need a `notification_kind` migration.
14. **Preparation details move with the reservation (AC11):** the move changes only its period, quantity and flag.
15. **A new safety check (AC10).** Settling a marked reservation, by either way, withdraws a safety approval in the same commit, naming the type and `reservation_reassessed`. It is usually already gone: a timing or quantity change is significant and withdrew it. A revision's own withdrawal comes first, so the event gets one entry.
16. **Default to review: no history entry for the marking or the move.** The edit's `field_changed` entries, the line's outcome entry and any withdrawal already say what happened.

### The gates (AC5, AC12)
17. **Both gates refuse while a reservation is marked,** through the shared `_equipment_gaps`, one line per reservation under `equipment`: "Equipment reservation 7 (Projector) is awaiting reassessment by Technical Support." A reopened line already holds both back, having no outcome. The summary messages are unchanged.

### A reservation never exceeds its line (AC9)
18. **Reserving is refused, on `quantity`, when with what the event already holds of the type it would pass the line:** "The event asks for 3 of these, and 2 are already reserved." **Default to review:** a type the event has no line for is reserved up to what is free, as before; decision 22 says how such a reservation is settled once marked.

### A reservation of a type with no line (added in review of PR #154)
22. **Default to review: confirming is the review of a reservation of a type the event has no line for.** A date or time change marks it like any other (AC1), but with no line there is no outcome to record, so before this decision nothing could settle it and both gates held the event back for good. Confirming now keeps what is free for the event's period now, up to what it holds, oldest first, and releases the rest, with no note, since the coordinator never asked for that equipment. Technical Support are told by the edit's `significant_change` notice when an edit marks such a reservation, though the event has no line (decision 3 sent it only to an event with a line). It does not appear on the awaiting-action list, which lists lines (SCRUM-38); the notice and the Equipment page show it. **Considered:** refusing a reservation without a line instead, which would change SCRUM-46's reserving (18 backend tests, mostly SCRUM-46's, reserve a type with no line) and leave reservations made before it stuck; left under "Revisit when".
23. **Each reassessment says whether confirming would settle it now (`confirmable`).** It is true when confirming would keep no more than is free: for a line with a current outcome, what the outcome provides, up to what is held; for a type with no line, always (decision 22). The Equipment page offers Confirm only then, and otherwise points to the outcome form, so it no longer offers a Confirm that the backend refuses (a reopened line, AC12, or a new quantity, AC8).

### Nothing more (decided before the build)
19. Nothing past SCRUM-60's criteria: no venue or hold work (SCRUM-59, SCRUM-99), and no notice to the coordinator when a change marks their reservations.

### The web app and the mock
20. **The Equipment page** gains "Reservations to reassess" when anything is marked: each type's reserved units, the period they hold, the period now, what is free and any shortfall. Technical Support get a Confirm button where the reassessment is `confirmable` (decision 23), saying what it keeps when something is short; otherwise the page points them to the outcome form above. The coordinator sees the same, with nothing to confirm. **The queue** on Staff home says "(reservation to reassess)" after each such line.
21. **The mock backend** answers both routes, settles marked reservations on an outcome, marks them on a new quantity and caps a reservation at its line. It starts with one moved event, `EVR-MOCK0004`, whose reservations a date change marked. **Not mirrored:** the edit mock keeps its own events, apart from the equipment mock's, so an edit there marks nothing, and the planning mock's gates know nothing of reservations. Both wait for the mocks to share one store of events (the ticket ADR-0107 decision 10 asks for).

## Consequences
- After a date or time change, every reservation of the event stays held for its old period, keeping those units from other events, until Technical Support act.
- An event with a marked reservation can't reach Safety Review or Confirmed; the refusal says which reservation.
- Technical Support can now trim a reservation, through a lowered line's outcome, which answers ADR-0092's "Not built".
- Integration tests: `frontend/src/integration/equipmentReassessment.int.test.ts`. Backend tests are marked `scrum_60`.

## Revisit when
- SCRUM-57 is built: its approval calls `reassess_equipment_after_timing_change` and tells Technical Support (decision 2).
- The team wants the coordinator told when a change marks their reservations, or a history entry for a move (decisions 16, 19).
- A reservation without a line should be refused outright (decisions 18, 22), or listed on the awaiting-action list.
- The mocks share one store of events (decision 21).
