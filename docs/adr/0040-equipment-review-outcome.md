# ADR-0040: Technical Support records how much of an equipment request can be met; the status is derived from the quantity provided

- **Status:** Accepted; the coordinator's notice gains the outcome and the note in [ADR-0055](0055-booking-and-equipment-notices.md)
- **Date:** 2026-10-13
- **Story:** SCRUM-48 Record the outcome of an equipment review

## Context
SCRUM-48 lets Technical Support staff record, line by line, how much of a requested equipment line they can provide: all of it (fulfilled), some of it (partially fulfilled, with the shortfall) or none of it (unavailable, with a reason). The coordinator is told, the outcome can be revised, and a revised outcome after the Operational Safety Check forces a new check. The ACs leave open where the outcome lives, who owns the status, what the shortfall is, when a note is required, who is notified and what happens to the Technical Support queue.

## Decision
1. **The outcome belongs to the line, not to a reservation.** `EquipmentReservation` rows (SCRUM-46) record what was actually held, keyed by event and type with no link to a line. The outcome is Technical Support's statement about a request, which may differ from reservations (they can declare "unavailable" without reserving anything). So it is stored on `EventEquipmentLine` (`provided_quantity`, `outcome_note`, `reviewed_by`, `reviewed_at`), not derived from reservations. Migration `0024_add_equipment_outcome` (file `0024_add_equipment_review_outcome.py`) adds the columns and the three enum values; the revision id is shortened because a longer one exceeded the `alembic_version` column's 32 characters.
2. **`provided_quantity` is the source of truth; the status is derived.** The service computes the status: `provided == quantity` is `fulfilled` (AC2), `0 < provided < quantity` is `partially_fulfilled` (AC1), `provided == 0` is `unavailable` (AC3). The caller never sends a status, so the two can never disagree. A `provided_quantity` above the line's `quantity` is a `400`.
3. **The shortfall is derived, never stored:** `quantity - provided_quantity` (AC1). It is a different quantity from `EquipmentAvailability.shortfall` in the equipment module, which measures availability against a request, so that name is not reused on the line.
4. **`provided_quantity IS NULL` means "no outcome recorded yet".** SCRUM-97 and SCRUM-49 gate Safety Review on every equipment request having an outcome, so `lines_without_outcome` and `all_outcomes_recorded` expose that seam by name and those stories do not re-derive it.
5. **A note is required whenever `provided < quantity`.** AC3 requires a reason when nothing is available, and AC1 shows a note beside a partial outcome. A fulfilled outcome needs none. A blank or whitespace-only note counts as missing. This is a judgement call (see decision 13).
6. **The coordinator is notified on every recorded outcome,** not only an unavailable one. AC3 names the notification explicitly, but SCRUM-97's team assumption says any outcome Technical Support records, including partial or unavailable, counts as their decision and the coordinator is notified of it (SCRUM-48). This is a judgement call (see decision 13).
7. **An outcome can be revised with no guard (AC5).** Recording again overwrites the columns and writes another history entry (`EventHistoryKind.EQUIPMENT_OUTCOME_RECORDED`), so the trail shows the revision. There is no "already recorded" conflict. The history entry is internal: it is hidden from organisers (`INTERNAL_ONLY_KINDS`).
8. **Recording an outcome takes the line off Technical Support's queue.** `list_equipment_requests_awaiting_action` filters on the `requested` status, so a line with an outcome drops out of it. This is the one existing behaviour the change alters, and it has a test.
9. **Where the outcome is shown.** `POST /api/events/requests/<reference>/equipment/<line_id>/outcome` (endpoint `events.record_outcome`, `technical_support_staff`) returns the line with its outcome. The outcome fields (provided quantity, shortfall, note, reviewer, time) also appear on the equipment list (`GET .../equipment`). The organiser's event detail (`EventRequestDetailSchema`) shows each line's status but not the provided quantity, shortfall, note, reviewer or time; a later story shares those.
10. **A line id belonging to another event is a `404`,** and an Event Coordinator calling the route is a `403`; only Technical Support records an outcome.
11. **Deferred acceptance criteria, each with its owner.**
    - AC6 (a revised outcome after the Operational Safety Check forces a new check): **SCRUM-97** and **SCRUM-98**, because Safety Review does not exist yet.
    - Notifications beyond the coordinator: **SCRUM-50**.
12. **Known gaps, each a default for the team to review (the organiser's detail page not showing the outcome is in decision 9).**
    - **Changing a line after an outcome is recorded can leave the outcome stale.** Lowering the quantity below `provided_quantity` is refused with a `400` on `quantity` (the database check would otherwise fire). Raising the quantity is allowed and leaves a `fulfilled` status beside a positive shortfall, and removing the line discards its outcome. A follow-up ticket for the team to raise in Jira: decide whether to block those edits once an outcome exists or to reset the outcome.
    - **`all_outcomes_recorded` returns `True` for an event with no equipment,** because no line is missing an outcome. SCRUM-97 and SCRUM-49 must decide whether an event with no equipment passes the Safety Review gate; this is what "every request has an outcome" means for zero requests.
    - **An outcome can be recorded on an event in any non-draft status,** including rejected, cancelled and completed, and the coordinator is still notified. A follow-up ticket for the team to raise in Jira: decide which statuses accept an outcome.
13. **Defaults to review (not agreed with the team):** decision 5 (a note is required for a partial outcome, not only an unavailable one), decision 6 (the coordinator is notified of every outcome, not only an unavailable one), and the three gaps in decision 12.

## Consequences
- The status can never disagree with the quantities, and the shortfall needs no migration to correct.
- Safety Review stories gate on `lines_without_outcome` / `all_outcomes_recorded` without new queries.
- Until the stale-outcome ticket is settled, a coordinator's edit to a line can make a recorded outcome misleading.
- The migration's downgrade loses recorded outcomes: it resets every line with an outcome to `requested`, nulls the four outcome columns, and deletes the `equipment_outcome_recorded` history entries and notifications.

## Revisit when
- SCRUM-97 / SCRUM-98 build Safety Review (AC6, and the empty-equipment question).
- The team answers the stale-outcome ticket.
- The team confirms or overturns decisions 5 and 6.
