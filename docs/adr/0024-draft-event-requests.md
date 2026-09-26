# ADR-0024: A draft is an event request in status draft: saved with only a name, seen only by its author, submitted in place under the full submission rules

- **Status:** Accepted
- **Date:** 2026-09-26
- **Story:** SCRUM-20 Save and resume a draft event request
- **Extends:** [ADR-0020](0020-organisers-see-their-organisations-events.md): the one condition an organiser's scope is decided by
- **Supersedes:** part of [ADR-0019](0019-event-equipment-lines.md): a draft is `404` to staff, not `409`; part of [ADR-0021](0021-coordinator-reassignment.md): reassigning a draft is `404`, not `409`

## Context
SCRUM-20's ACs say: an Organiser can save a request with only the event name; a saved draft shows status Draft and is visually distinct from submitted requests in the event list; an Organiser can reopen a draft, change any field and save it again; a draft is visible only to the Organiser who created it and never appears to Event Coordinators. The story has no comments.

Left open:
1. **Where a draft lives.** A new table, or a row in `event_requests` with a new status.
2. **How a name-only request fits the schema,** when five columns (`proposed_date`, `end_date`, `start_time`, `end_time`, `expected_attendance`) are `NOT NULL`.
3. **The draft's reference.** SCRUM-19 gives every request an `EVR-…` reference on save (ADR-0004); nothing says whether a draft has one yet, or keeps it once submitted.
4. **The route shape** for saving, editing and submitting a draft.
5. **Edit semantics:** whether a `PATCH` replaces the draft or changes only what is sent, and what a field sent as `null` does.
6. **How much validation runs on a save or an edit,** when most of SCRUM-19's rules (ADR-0001, ADR-0002) need fields a draft may not have yet.
7. **How a draft is submitted:** through the same `POST /requests` with everything resent, or a dedicated action on the stored draft.
8. **What `end_date` does** when a draft is saved with a `proposed_date` but no `end_date`.
9. **An organiser with no client organisation** (ADR-0013): can they save an unfiled draft?
10. **Where "visible only to its author" is enforced,** given `_visible_to_organiser` already scopes every organiser's request to their organisation (ADR-0020).
11. **What a colleague's draft, and a request that is no longer a draft, answer** to draft-only routes.
12. **What internal staff see.** Coordinators and Technical Support look requests up by reference for equipment and reassignment (ADR-0019, ADR-0021); none of those checks currently rules out a draft.
13. **Whether SCRUM-38's awaiting-equipment list needs a change.**
14. **Whether a draft can be deleted.**
15. **Whether saving or editing a draft writes to the event history, or notifies anyone.**
16. **List order,** and what a submitted draft's `created_at` is.
17. **The submit response's shape and status code.**
18. **What downgrading the schema migration does** to a draft with empty details.
19. **How the newly-nullable columns are typed** on the model.
20. **Whether drafts are capped or expire.**
21. **What "visually distinct" means** to the backend, which draws no UI.

## Decision
1. **A draft is a row in `event_requests` with `status = 'draft'`** (20-1), not a separate table: every later story that reads a request (equipment, reassignment, history) keeps working on it unchanged once it leaves draft, and "reopen" is just "look it up" and "edit" just "update the row in place".
2. **Five columns become nullable** — `proposed_date`, `end_date`, `start_time`, `end_time`, `expected_attendance` — **guarded by a check constraint**, `ck_event_requests_details_unless_draft`: `status = 'draft' OR (`all five `IS NOT NULL)` (20-2). The alternative, keeping them `NOT NULL` with placeholder values, was rejected: a placeholder is indistinguishable from a real answer everywhere else that reads the row, and AC2's `null` details depend on there being nothing to placeholder. `ck_event_requests_expected_attendance_min` (`expected_attendance >= 1`) stays: a `CHECK` passes on `NULL`, so it only ever bites a value that is actually there.
3. **A draft gets its `EVR-…` reference at first save, and keeps it if submitted** (20-3): one identifier for the whole lifetime of a request, so a link or a note taken while it was a draft still resolves afterwards. Reference collisions are retried exactly as a fresh submission's are (ADR-0004); the retry loop is shared (`_save_under_new_reference`) so both paths retry, log and give up the same way.
4. **Three routes** (20-4): `POST /api/events/requests/drafts` (save), `PATCH /api/events/requests/drafts/<reference>` (edit), `POST /api/events/requests/drafts/<reference>/submit` (submit). Reopening a draft is just `GET /api/events/requests/<reference>`, already an organiser's own. A `draft: true` flag on `POST /requests`, or folding editing into `PATCH /requests/<reference>`, were rejected: a draft's validation is different enough from a submitted request's (decision 6) that sharing the route would need the same branching a separate one avoids, and `PATCH /requests/<reference>` does not exist for any other status.
5. **Editing is a partial `PATCH`** (20-5): only the fields sent change; a field sent as `null` clears it; the `name` cannot be cleared, since it is what a saved draft is titled by in the reopened list; an empty body is a valid `200` that changes nothing. `PUT`-style whole-document replacement was rejected: an organiser editing one field of a large draft should not have to resend every other one.
6. **Only per-field rules run on a save or an edit; rules that compare two fields or need "today" wait for submission** (20-6, extending decision 2's split): a draft may already hold a proposed date in the past, or an end time before the start, because it is not going ahead yet (ADR-0001, ADR-0002). Running every rule on every field supplied was rejected: it would refuse a perfectly good in-progress draft for not yet having the field the other side of the comparison.
7. **Submitting takes no body: the stored draft is loaded straight into `SubmitEventRequestSchema`** (20-7). A missing or rule-breaking detail is reported exactly as `POST /requests` reports it — down to "Missing data for required field." for one never supplied — because `_draft_as_payload` dumps the draft and drops every `None`, so an absent detail is absent from the payload rather than sent as an explicit `null`. Accepting final changes in the submit body was rejected: that would make submitting a second, undocumented way to edit a draft.
8. **`end_date` is kept exactly as sent and is only defaulted to `proposed_date` on submission** (20-8): `SubmitEventRequestSchema` keeps its own `end_date`-defaulting hook, which `SaveDraftSchema` (used to save and edit) does not run. Defaulting it at save time was rejected: a later edit to `proposed_date` alone would then leave a stale `end_date` no one asked for.
9. **An organiser with no client organisation is refused `403` on save, edit and submit** (20-9), the same answer `OrganiserWithoutOrganisationError` already gives a fresh submission (ADR-0013) and the organiser's own list (ADR-0020). An unfiled draft was rejected: nothing else in the system reads a request with no organisation (ADR-0020), so it could be saved but never seen again.
10. **Draft scope lives in the one place organiser scope already lives:** `_visible_to_organiser` (20-10). It now reads `organisation_id = caller's organisation AND (status != draft OR organiser_id = caller)`: every request of the caller's organisation, plus their own drafts, minus everyone else's. A separate filter per view was rejected: ADR-0020 already treats this condition as the single source of truth for "what an organiser may see", and a second copy could drift from it.
11. **A colleague's draft is `404`, indistinguishable from an unknown reference** (20-11), same as ADR-0012's rule for another organisation's request. **A request that is no longer a draft, asked for by a draft-only route, is `409 request_not_draft`**, `"Only a draft event request can be changed or submitted this way."` — distinct from the `404`, because the organiser *can* see the request (it is theirs, past the draft stage); it just cannot be edited or submitted as a draft any more. Answering both the same way was rejected: an organiser who submitted their own draft and then mistakenly retries the submit route deserves "already done", not "not found".
12. **Every staff lookup by reference goes through one guarded path** (20-12): `_event_request_by_reference` now requires `belongs_to` (no caller may look a row up unscoped by accident), and a new `_event_request_for_staff` composes it with `_not_a_draft()`. `_event_request_assigned_to` (equipment, ADR-0019), the Technical Support branch of `list_equipment_lines`, and `reassign_coordinator` (ADR-0021) all use it, so a draft is `404` to every internal role — even a coordinator the draft happens to name, since it was never really assigned anything. Relying on the coordinator column being `NULL` was rejected: SCRUM-24's future "pick up an unassigned request" would then be indistinguishable from "open a draft".
13. **SCRUM-38's awaiting-equipment list needs no change today** (20-13): a draft cannot yet hold an equipment line (decision 12 hides it from the very routes that add one), so it can never appear.
14. **Deleting a draft is out of scope** (20-14): no AC asks for it, and it can wait for a story that does.
15. **Saving or editing a draft writes no history and notifies nobody** (20-15): nothing has happened to it that any other role needs to hear about. Submitting one writes the same `coordinator_assigned` entry, and sends the same notification, that a fresh submission does (`_mark_submitted`, shared by both).
16. **The list order is unchanged: newest `created_at` first, drafts and submitted requests mixed together** (20-16), and a submitted draft keeps the `created_at` it was saved with — it does not jump to the top just for having been submitted. A separate "drafts first" section, or sorting by `submitted_at`, were rejected: no AC asks for a distinct ordering, and adding one would be speculative.
17. **Save answers `201`; edit and submit both answer `200`** (20-17), each with the same `EventRequestSchema` every other event-request response uses, so a client renders a draft with the same code that renders anything else. `EventRequestSchema` gains `allow_none=True` on the five detail fields, and a "days left" caller (`_group_lines_by_event`) gets a `# type: ignore[operator]`: the query it reads from already excludes drafts, so a live `None` there would be a bug, not an expected case.
18. **Downgrading migration 0014 deletes any draft still missing a detail, before restoring `NOT NULL`** (20-18): there is no value to invent for a required column on a row that was allowed to have none. This is lossy, like migrations 0006 and 0010's rollbacks, and is spelled out in the migration's docstring. Refusing to downgrade at all was rejected: every other migration in this codebase downgrades unconditionally, even destructively, and a special case here would break that expectation.
19. **The five columns become `Mapped[T | None]`** (20-19), matching `nullable=True` as every other optional column in this codebase does; the one place that cannot express "no date" any other way (`_group_lines_by_event`'s day-count) gets a comment and a targeted `# type: ignore[operator]` rather than a runtime `None` guard that can never actually run.
20. **No cap or expiry on drafts** (20-20): nothing in the story asks for one.
21. **"Visually distinct" is met with data, not a rendering hint** (20-21): the list already carries `status: "draft"` and the detail fields as `null`; a client tells a draft apart from a submitted request by exactly the same fields it already reads for everything else. A dedicated `is_draft` flag, or a second, split list, were rejected as saying the same thing the status already says.

Checks run in this order everywhere, so the first failure decides the answer:
- **Save:** `400` payload → `403` no organisation → save.
- **Edit:** `400` payload → `403` no organisation → `404` no such draft (including a colleague's) → `409` not a draft → save.
- **Submit:** `403` no organisation → `404` no such draft → `409` not a draft → `400` a detail is missing or fails a rule → save.

## Consequences
- Every place that reads `proposed_date`, `end_date`, `start_time`, `end_time` or `expected_attendance` from an `EventRequest` must allow for `None`; today that is only `_group_lines_by_event`, protected by decision 12 keeping drafts out of its query.
- **SCRUM-24's list of unassigned requests must filter on `status == submitted`, not only `coordinator_id IS NULL`,** or a draft (which also has no coordinator) would appear in it.
- Any new staff lookup by reference must go through `_event_request_for_staff`, and any new staff list must apply `_not_a_draft()`, or it will leak a draft the same way the pre-SCRUM-20 equipment and reassignment routes did.
- SCRUM-33's future edit-history route only ever applies past the draft stage: nothing a draft's own save or edit does is written to history.
- A request submitted from a draft keeps the `created_at` of when it was first saved as a draft, not when it was submitted; a story that wants "time since submission" will need a new column.
- Rolling back migration 0014 deletes any draft that never got its full details.
- `mypy` is not in CI yet; when it joins, the `# type: ignore[operator]` in `_group_lines_by_event` and the `Mapped[T | None]` columns are the two places this story's typing decisions should be re-checked.

## Revisit when
- A story lets an organiser share a draft with a colleague, or delete one, or asks for drafts to expire.
- SCRUM-23 or another story needs to move a request back to `draft` after submission: decision 11's `409` and decision 12's staff-hiding would both need to apply again.
- SCRUM-24 lands: revisit its unassigned-requests filter (see Consequences) and whether picking up a request and reopening a draft should read any more alike than they do today.
- A story wants `submitted_at` distinct from `created_at`, or a distinct sort for drafts.
- Mypy joins CI: re-check the columns and the call site this ADR marks as typed around a gap.
