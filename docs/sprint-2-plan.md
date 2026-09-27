# Sprint 2 plan: the remaining tickets as stacked rounds

This is a working plan for finishing Sprint 2 in parallel batches. It is written as a handoff so a
new session can pick it up. Requirements still live only in Jira (`SCRUM-<n>` on
`smu-team-uu78imq6.atlassian.net`), so this file lists order and dependencies, not ACs. Read each
story's ACs and comments in Jira before planning it.

Written 2026-09-25, when `main` was at `bf4652c`. Updated 2026-09-27 after rounds 4 and 5.

Sprint 2 ends on 2026-10-04. Sprint 3 runs from 2026-10-04 to 2026-10-18.

## Where things stand

**Every Sprint 2 story that can be built this sprint is built and in review.** #17 has merged. The
rest form one stack of 21 PRs, each based on the one listed above it. Every PR has keene-ng-2024 as
a reviewer. Only #18 is approved so far.

| # | PR | Branch | Migration | ADR |
|---|---|---|---|---|
| — | #17 SCRUM-22 event status model | merged | 0006 | 0012 |
| 1 | #18 SCRUM-66 client organisations | `feat/SCRUM-66-client-organisations` (base `main`) | 0007 | 0013 |
| 2 | #19 SCRUM-27 equipment catalogue | `feat/SCRUM-27-equipment-catalogue` | 0008 | 0014 |
| 3 | #20 SCRUM-28 notifications | `feat/SCRUM-28-notifications` | 0009 | 0015 |
| 4 | #21 SCRUM-34 block a venue | `feat/SCRUM-34-block-venue` | none | 0016 |
| 5 | #22 SCRUM-36 venue suitability | `feat/SCRUM-36-venue-suitability` | none | 0017 |
| 6 | #24 SCRUM-30 assign a coordinator | `feat/SCRUM-30-assign-coordinator` | 0010 | 0018 |
| 7 | #25 SCRUM-37 event equipment | `feat/SCRUM-37-event-equipment` | 0011 | 0019 |
| 8 | #26 SCRUM-5/40 CI on every PR | `ci/SCRUM-5-stacked-pr-checks` | none | none |
| 9 | #28 SCRUM-7 organisation's events | `feat/SCRUM-7-organisation-events` | none | 0020 |
| 10 | #29 SCRUM-87 reassign a coordinator | `feat/SCRUM-87-reassign-coordinator` | 0012 | 0021 |
| 11 | #30 SCRUM-38 equipment awaiting action | `feat/SCRUM-38-equipment-awaiting-action` | 0013 | 0022 |
| 12 | #32 SCRUM-88 staff accounts by command | `feat/SCRUM-88-staff-registration` | none | 0023 |
| 13 | #33 SCRUM-20 drafts | `feat/SCRUM-20-draft-requests` | 0014 | 0024 |
| 14 | #34 SCRUM-33 edit an event, with history | `feat/SCRUM-33-edit-event-history` | 0015 | 0025 |
| 15 | #35 SCRUM-24 each role's event lists | `feat/SCRUM-24-role-event-lists` | none | 0026 |
| 16 | #36 SCRUM-68 mark an event completed | `feat/SCRUM-68-complete-event` | 0016 | 0027 |
| 17 | #37 SCRUM-31 review and decide | `feat/SCRUM-31-review-decide` | 0017 | 0028 |
| 18 | #38 SCRUM-32 ask for clarification | `feat/SCRUM-32-clarification` | 0018 | 0029 |
| 19 | #39 SCRUM-39 assignment notices | `feat/SCRUM-39-decision-notifications` | 0019 | 0030 |
| 20 | #40 SCRUM-41 end-to-end journey | `feat/SCRUM-41-e2e-journey` | none | 0031 |

#27 (SCRUM-5, the PR description template) is separate, based on `main`.

- **Next free numbers:** migration **0020**, ADR **0032**.
- **Checks:**
  - Every commit passes lint, format and tests on its own.
  - `diff-cover` is 100% for each PR against the branch below it.
  - The migration chain 0001 to 0019 was checked on Postgres 16, on the top of the stack: one head, upgrade, `db check`, downgrade to base, upgrade.
  - The tip has 1491 tests; `pytest -m "not e2e"` gives 1487.
- **CI:** it runs on every PR whatever its base, measures `diff-cover` against the PR's own base, and posts the coverage as a comment.
- **Merging:** bottom up, with **Rebase and merge**. Automatic branch deletion is **off**, so delete each merged branch by hand. GitHub then retargets the next PR to `main`.
- **Review is the bottleneck.** With 20 open PRs in one stack, a change requested low down means rebasing everything above it. Get #18 to #26 reviewed first.
- **Open with the repo owner:** make *Backend — migrate + unit tests* a **required** status check on `main`. SCRUM-41's AC2 ("a failure blocks the merge") depends on it (ADR-0031, 41-10).

This file sits on its own branch, `docs/sprint-2-plan`. **Don't build on this branch.** Start new
work from `feat/SCRUM-41-e2e-journey`, the top of the stack, or from `main` once the stack has merged.

## What earlier rounds give later stories

- **Notifications:** `notify_users(recipient_ids, EventSummary(id, reference, name), NotificationKind.X, *, session=None)`
  in `app.modules.notifications.services` (SCRUM-28). A new kind needs an enum member, its
  message, and a migration that runs `ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS` in an
  autocommit block (copy 0010). Inside the events module, `_raise_notifications(...)` wraps it and
  logs a failure instead of raising it.
- **Who is told about a new request:** only the assigned coordinator, with
  `coordinator_assigned`. SCRUM-28's broadcast to every coordinator is gone (ADR-0018).
- **Users by role:** `list_user_ids_with_role(role)` in `app.modules.auth.services`.
- **Shared validation:** `WholeNumber` in `app.common.fields`, and `not_blank` and `load_or_raise`
  in `app.common.validation`.
- **Suitability:** `check_venue_suitability` in `app.modules.venue.services`. SCRUM-42 will call
  it to require a justification when a venue is unsuitable.
- **Event statuses (ADR-0012, 0028, 0029):** nine: `draft`, `submitted`, `under_review`,
  `awaiting_clarification`, `approved`, `confirmed`, `completed`, `cancelled`, `rejected`. Any
  migration that rebuilds `event_request_status` must drop and re-create 0014's
  `ck_event_requests_details_unless_draft` around the re-type (see 0017 and 0018).
- **Event requests:** they carry `organiser_id`, `organisation_id` and `coordinator_id`.
  Submitting refuses an organiser who has no organisation, so test fixtures must give organisers
  one (see `organiser_is_found` and `saved_users`).
- **Event history (SCRUM-30, ADR-0018):** `record_event_history(event_request, kind, *, actor_id, details=None, session=None, now=None)`
  adds an entry **without committing**, so it is saved in the same commit as the change it
  records. `actor_id = None` means the system did it. Kinds so far: `coordinator_assigned` (id
  only) and `coordinator_reassigned` (ids and names).
- **Coordinator ownership:** `_check_assigned_to(actor_id, event_request)` answers 404 when the
  caller isn't the event's coordinator. The equipment routes and reassignment both use it.
- **Organiser scope (SCRUM-7, ADR-0020):** `_visible_to_organiser` is the one SQL condition for
  what an organiser can see: every request in their organisation. SCRUM-20 narrows it there to hide
  other organisers' drafts.
- **Equipment lines (SCRUM-37, ADR-0019):** one line per equipment type on an event, editable by
  the assigned coordinator while the event is `submitted` or `under_review`. Every line is
  `requested`; SCRUM-46 adds `reserved`. Technical Support's list of what's awaiting them
  (SCRUM-38) is every upcoming event with a `requested` line.

- **Drafts (SCRUM-20, ADR-0024):** a draft is a `draft`-status row with nullable details. Staff lookups (`_event_request_for_staff`) exclude drafts with a 404.
- **Editing and history (SCRUM-33, ADR-0025):** `update_event_request` records one `field_changed` entry per field, and a significant change asks Technical Support to recheck equipment. `_record_field_changes` and `_EditedTimingSchema` are shared with SCRUM-32's resubmit.
- **Decisions (SCRUM-31, ADR-0028):** `start_event_request_review` and `decide_event_request`. The current decision is the latest `decision_recorded` entry. `_has_arrangements` is where SCRUM-42 adds venue booking requests.
- **Clarification (SCRUM-32, ADR-0029):** `request_clarification` and `resubmit_event_request`. `EventRecord` carries `coordinator`, `decision` and `clarifications`.
- **Notifications carry a `detail`** (the reason or the question/answer text). The organiser gets `request_assigned` on every assignment (SCRUM-39, ADR-0030).
- **Completion (SCRUM-68, ADR-0027):** `complete_event_request`, for a confirmed event after its end. Nothing sets `confirmed` until SCRUM-49.
- **End-to-end tests (SCRUM-41, ADR-0031):** `tests/e2e/` drives the app with Flask's test client (`Actor`, `sign_in`). It's the only place a test client is used.

## What's left in Sprint 2

**Nothing buildable.** Done: 22, 66, 27, 28, 34, 36, 30, 37, 5/40, 7, 87, 38, 88, 20, 33, 24, 68,
31, 32, 39, 41 (all in review; 22 merged).

- **SCRUM-84** (venue preparation details) and **SCRUM-85** (equipment preparation details) are in the sprint, but need SCRUM-42 and SCRUM-46, which are Sprint 3. Move them to Sprint 3.
- **Parts deferred to Sprint 3, each recorded in its ADR:**
  - SCRUM-24's Venue Staff and Attendee lists (42, 52);
  - SCRUM-33 and SCRUM-31's venue-booking halves (42);
  - SCRUM-68's "no new registrations" (52).

### Sprint 3, next

- **SCRUM-42** (request a venue for an event): it calls `check_venue_suitability`, and adds venue booking requests to `_has_arrangements` (31) and `_reassess_arrangements` (33).
- **SCRUM-46** (reserve equipment), then 84 and 85.
- **SCRUM-49** (confirm an event), which unlocks completing one for real (68).
- **SCRUM-52** (attendee registration).

### Tickets to open (collected from the PRs)

- Organisers can register under a guessed organisation id (ADR-0013, from SCRUM-88).
- Pick up an unassigned request (ADR-0018, 0021, 0026).
- Extract the shared "assigned coordinator + status guard" check (four copies after 31 and 68).
- A "needs your answer" list for organisers (ADR-0029, 32-9).
- Run the e2e journey against CI's Postgres, and add a rejection journey (ADR-0031).
- Customer questions: SCRUM-23 (is `approved` a status?), SCRUM-68 (manual or automatic completion), SCRUM-33's clarification label, and SCRUM-65 (who provisions staff accounts).

## Decisions that unblock the most

1. **"Approved" status:** **settled for now.** It's an eighth status, and `awaiting_clarification` a ninth (ADR-0028, ADR-0029). Confirm with the customer (SCRUM-23).
2. **Coordinator assignment rule:** **settled** (ADR-0018).
3. **SCRUM-36 input:** requirements, or an event id? Needed by SCRUM-42 (ADR-0017). **Open.**
4. **Registration security:** staff accounts now come from a command (SCRUM-88, ADR-0023). Organisation-id guessing is still a ticket to open. **Partly open.**
5. **Role limits:** should routes follow each story's Roles field? **Open.**
6. **SCRUM-33 AC2's venue half:** a hook is left for SCRUM-42 (ADR-0025). **Settled.**

## How the rounds were run, to repeat

- **One agent per ticket:** each runs in its own git worktree under `../spm-worktrees/SCRUM-<n>`,
  on branch `feat/SCRUM-<n>-<slug>`, created from the top of the stack. It commits locally only.
- **Planner then executor:** inside each ticket agent, a planner (`Plan` agent) reads `CLAUDE.md`,
  `backend/CONVENTIONS.md`, the review checklist, the ADRs and Jira (read-only), and returns a
  test-first plan. An executor (`general-purpose`) implements it and meets the definition of done
  in `CLAUDE.md`. The ticket agent then reviews the diff and checks each commit on its own. Rounds 1
  and 2 used a Fable planner and an Opus executor; round 3 used Opus for both.
- **Reserved numbers:** each agent gets a migration number and an ADR number up front, so file
  names don't collide.
- **Decisions are batched:** agents don't stop to ask. They build the conventional default and
  return a "Decisions made" table. The tables go into a log, `../spm-worktrees/DECISIONS.md`
  (round 2) or `DECISIONS-round3.md`, and are reviewed together before stacking. Anything flipped
  goes back to the ticket agent before the PRs open.
- **The venv lives in the main checkout:** `backend/.venv`. From a worktree's `backend/`, run
  `<main>/backend/.venv/bin/pytest` and the other tools the same way, after checking that
  `import app` resolves to the worktree.
- **Postgres checks in parallel** need a different port and container name for each agent.
- **No attribution:** no `Co-Authored-By` line or any AI attribution in commits or PRs.

- **Round 5 (the process to keep):**
  - A Fable planner writes a test-first plan per ticket. An Opus executor implements it. A **separate test runner** (Sonnet) witnesses every RED step before any code is written, then runs a final gate: every commit on its own, plus diff-cover.
  - The process is written down in `../spm-worktrees/plans/PROTOCOL.md`.
  - For small REDs, the orchestrator can witness them with a script (the diff, the named tests, the full suite) in about 2–3 minutes, against about 10 for the runner.
  - For a test-only ticket (the e2e journey), the RED is **mutation checks**: break one line at a time in a scratch copy, and confirm the test goes red at the right step.
- **Replay migrations on Postgres while writing them.** Give each executor a throwaway Docker container on its own port, not only the orchestrator at stacking time.
- **Parallel commits only when they're independent.** SCRUM-32's C9 read history directly, so it could be built in parallel with C5–C8 and cherry-picked after.

## Stacking the branches afterwards (lessons from rounds 1 to 5)

1. **Keep a backup** before rebasing: `git branch backup/SCRUM-<n>-pre-stack`.
2. **Rebase in order.** Rebase each branch onto the one below it, in the stack order.
3. **Re-chain and renumber migrations.** Each new migration's `down_revision` (and its `Revises:`
   line) must point at the previous branch's revision. If a reserved number went unused, renumber
   the later migrations to close the gap: the file name, the `revision` id (≤ 32 characters),
   and the migration test's file name. Also delete any "re-chained later" note in the docstring.
   Fold each fix into the migration's own commit:
   - a plain fixup: `git commit --fixup=<sha>`;
   - a fixup that also rewords the commit message:
     `GIT_EDITOR="cp <message file>" git commit --fixup=amend:<sha>`;
   - then `GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash <base>`.
4. **Keep both sides of simple conflicts.** These conflict because two branches added lines in the
   same place:
   - `pytest.ini` markers (sort them by number);
   - the README module list, route table and marker list;
   - `docs/adr/README.md`;
   - the `_register_modules` import list;
   - new sections at the end of `services.py`, `schemas.py` and `routes.py`;
   - module and fixture docstrings, such as `make_event_request`'s.

   When merging two docstrings, check that neither side's wording is now wrong, e.g. a count of
   parameters.
5. **Watch for conflicts git can't see.** Seen so far:
   - One branch still called a private helper that another branch had moved to `app/common`.
     Lint caught it.
   - Tests submitted as an organiser with no organisation after SCRUM-66 made that a 403. The
     tests caught it.
   - Two branches made the same move of `WholeNumber` or the migration helpers. The files were
     identical, so git merged them cleanly or the commit became empty.
   - A migration test asserted its enum values equal the whole model, and a later migration broke
     it. Check that only its own values are a subset of the model's.
6. **Check every commit, not only the tip.** Check out each commit in a scratch worktree and run
   ruff check, ruff format --check and pytest. For about 18 commits this takes around 8 minutes, so
   run it in the background. Then, at each branch tip, run
   `diff-cover coverage.xml --compare-branch=<branch below>`.
7. **Run the migration chain on a throwaway Postgres:**
   ```bash
   docker run -d --rm --name pg-check -e POSTGRES_USER=cs -e POSTGRES_PASSWORD=cs -e POSTGRES_DB=cs -p 55439:5432 postgres:16-alpine
   DATABASE_URL=postgresql+psycopg2://cs:cs@localhost:55439/cs FLASK_APP=wsgi \
     flask db heads && flask db upgrade && flask db check && flask db downgrade base && flask db upgrade && flask db check
   docker stop pg-check
   ```
8. **Open the PRs bottom up,** each `--base` on the branch below. Use the PR template from #27:
   - split "Decisions made" into what was agreed in review and the defaults left to review;
   - give "What to check" and "Tickets to open" sections;
   - add a "Stack" section listing the whole stack, marking this PR, and stating the merge order.

   Then request the reviewer.

9. **Lessons from rounds 4 and 5:**
   - **Never run `git stash`.** The stash is shared across worktrees, and in round 4 an agent popped another ticket's stash.
   - **Alembic revision ids are at most 32 characters** (`alembic_version.version_num`).
   - **A rebuilt enum type needs its dependants dropped first:** constraints that compare the column block the re-type on Postgres (bug journal, 2026-09-27).
   - **A subclass schema reorders marshmallow fields:** inherited fields come first. Pin the order with `Meta.fields` where the order matters (history).
   - **"Keep both sides" can split a shared closing line** (`),` or `]`) between the two sides. Run ruff after every resolution, and never chain `git add` after a failing check.
   - **Re-chain each migration's `PREVIOUS_*` tuples** to include every kind the branches below added, in Postgres (append) order.
   - **Secret scanners flag strong-looking test passwords.** Reuse an existing fixture's value (`valid_registration_payload`) rather than adding a new literal.

