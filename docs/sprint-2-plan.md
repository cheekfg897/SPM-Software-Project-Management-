# Sprint 2 plan: the remaining tickets as stacked rounds

This is a working plan for finishing Sprint 2 in parallel batches. It is written as a handoff so a
new session can pick it up. Requirements still live only in Jira (`SCRUM-<n>` on
`smu-team-uu78imq6.atlassian.net`), so this file lists order and dependencies, not ACs. Read each
story's ACs and comments in Jira before planning it.

Written 2026-09-25, when `main` was at `bf4652c`.

## Where things stand

Round 1 is six stacked PRs, each based on the one below it:

| # | PR | Branch | Migration | ADR |
|---|---|---|---|---|
| 1 | #17 SCRUM-22 event status model | `feat/SCRUM-22-event-status-model` (base `main`) | 0006 | 0012 |
| 2 | #18 SCRUM-66 client organisations | `feat/SCRUM-66-client-organisations` | 0007 | 0013 |
| 3 | #19 SCRUM-27 equipment catalogue | `feat/SCRUM-27-equipment-catalogue` | 0008 | 0014 |
| 4 | #20 SCRUM-28 notifications | `feat/SCRUM-28-notifications` | 0009 | 0015 |
| 5 | #21 SCRUM-34 block a venue | `feat/SCRUM-34-block-venue` | none | 0016 |
| 6 | #22 SCRUM-36 venue suitability | `feat/SCRUM-36-venue-suitability` | none | 0017 |

- **Checks:** every commit passes lint, format and tests on its own. `diff-cover` is 100% for
  each PR against the branch below it. The migration chain 0001 to 0009 was checked on
  Postgres 16: upgrade, `db check`, downgrade to base, upgrade.
- **Merging:** bottom up, with **Rebase and merge**. Automatic branch deletion is **off** in
  this repo, so delete each merged branch by hand. GitHub then retargets the next PR to `main`.
- **CI:** the workflows only run on PRs that target `main`, so a PR in the middle of the stack
  gets its checks only once it's retargeted. Round 2 fixes this (SCRUM-5).

This file sits on its own branch, `docs/sprint-2-plan`, on top of #22. **Don't build on this
branch.** Start each round-2 branch from `feat/SCRUM-36-venue-suitability`, or from `main` once
the stack has merged.

## What round 1 gives later stories

- **Notifications:** `notify_users(recipient_ids, EventSummary(id, reference, name), NotificationKind.X, *, session=None)`
  in `app.modules.notifications.services` (SCRUM-28). A new kind needs an enum member, its
  message, and a migration that runs `ALTER TYPE notification_kind ADD VALUE`.
- **Users by role:** `list_user_ids_with_role(role)` in `app.modules.auth.services`.
- **Shared validation:** `WholeNumber` in `app.common.fields`, and `not_blank` and `load_or_raise`
  in `app.common.validation`.
- **Suitability:** `check_venue_suitability` in `app.modules.venue.services`. SCRUM-42 will call
  it to require a justification when a venue is unsuitable.
- **Event statuses (ADR-0012):** `draft`, `submitted`, `under_review`, `confirmed`, `completed`,
  `cancelled`, `rejected`.
- **Event requests:** they carry `organiser_id` and `organisation_id`. Submitting refuses an
  organiser who has no organisation, so test fixtures must give organisers one (see
  `organiser_is_found` and `saved_users`).

## Dependency chain

Tickets inside one round don't depend on each other. Every ticket in a round depends on
something in an earlier round.

### Round 2: can start now

| Ticket | Needs | Notes | Migration | ADR |
|---|---|---|---|---|
| SCRUM-30 Assign a coordinator automatically | 22, 28 | Choose an assignment rule (round-robin or least-loaded) and record it in an ADR. **Add a shared event history table here**, because 31, 87 and 33 all need one. | 0010 | 0018 |
| SCRUM-7 See only my own organisation's events | 66 | The list and detail views switch from filtering by the submitting organiser to filtering by organisation. | probably none | 0019 if needed |
| SCRUM-37 Record what equipment an event needs | 27, 28 | Equipment lines on an event request. Notify Technical Support Staff through `notify_users`. | 0011 | 0020 if needed |
| SCRUM-5 / SCRUM-40 leftovers | none | Run CI on every PR, not only PRs that target `main` (this fixes stacked PRs). Post the coverage figure on the PR. No app code. | none | none |

Two SCRUM-5 ACs are repo settings only an admin can change: blocking merges while CI fails, and
requiring an approving review.

Suggested stack order: **30 → 7 → 37 → CI**. 30 and 7 both touch events submit and list; putting 30
first keeps the conflicts small.

### Round 3: after SCRUM-30 (and SCRUM-37)

| Ticket | Needs | Notes |
|---|---|---|
| SCRUM-31 Review and decide a request | 30 | **Blocked on a decision:** it uses an "Approved" status that isn't among ADR-0012's seven (the open subtask SCRUM-23 asks the customer). Record decisions in the event history. |
| SCRUM-87 Reassign a coordinator | 30 | The previous assignment goes in the event history. |
| SCRUM-20 Save and resume drafts | 22, 7, 30 | Held back from round 2 on purpose. Other organisers in the same organisation mustn't see a draft (interacts with 7). A draft is assigned only when submitted (interacts with 30). Saving a draft sends no notification (interacts with 28). |
| SCRUM-33 Edit event info with change history | 30 | Change history and the editable fields can be built now. "A significant change triggers reassessment" waits for bookings (SCRUM-42). |
| SCRUM-38 Equipment requests awaiting action | 37 | |

### Round 4

| Ticket | Needs | Notes |
|---|---|---|
| SCRUM-32 Ask the organiser for clarification | 31 | Uses the `under_review` status. |
| SCRUM-68 Mark an event completed | 30, 33 | "Can no longer be edited" relies on 33. Nothing sets Confirmed until SCRUM-49 (Sprint 3), so tests set the status directly. |
| SCRUM-24 See the events my role is involved in | 7, 30 | Only the organiser and coordinator views can be built now. The Venue Staff, Technical Support and attendee views wait on 42, 37 and 52. |
| SCRUM-39 Notifications for review decisions | 30, 31, 32, 87 | Better for 30, 31, 32 and 87 to send their own notifications. 39 then fills gaps, such as telling the organiser a coordinator was assigned. |

### Round 5

- **SCRUM-41**, the end-to-end test from request to approval: draft → submit → assign → clarify →
  resubmit → approve. Needs 20, 30, 31 and 32.

### Can't start in Sprint 2

- **SCRUM-84** needs venue bookings (SCRUM-42, Sprint 3).
- **SCRUM-85** needs equipment reservations (SCRUM-46, Sprint 3).

## Decisions that unblock the most

1. **"Approved" status:** is it an eighth status, or does approval move a request to
   `under_review`/Planning? Blocks SCRUM-31 (see ADR-0012 and SCRUM-23).
2. **Coordinator assignment rule:** round-robin, least-loaded, or something else? Needed for
   SCRUM-30.
3. **SCRUM-36 input:** should the suitability check take an event id instead of requirements
   (ADR-0017)?
4. **Registration security:** public registration lets anyone register under any organisation id
   they guess (ADR-0013, SCRUM-88). Settle this before SCRUM-7 exposes an organisation's events.
5. **Role limits:** should routes follow each story's Roles field? SCRUM-34's field lists Event
   Coordinator, but its routes are Venue Staff only.

## How round 1 was run, to repeat for round 2

- **One agent per ticket:** each runs in its own git worktree and branch,
  `feat/SCRUM-<n>-<slug>`, and commits locally only.
- **Planner then executor:** inside each ticket agent, a **Fable** planner (`Plan` agent) reads
  `CLAUDE.md`, `backend/CONVENTIONS.md`, the review checklist, the ADRs and Jira (read-only), and
  returns a test-first plan. An **Opus** executor (`general-purpose`) implements it and meets the
  definition of done in `CLAUDE.md`. The ticket agent then reviews the diff.
- **Reserved numbers:** each agent gets a migration number and an ADR number up front, as in the
  round 2 table, so file names don't collide.
- **The venv lives in the main checkout:** `backend/.venv`. From a worktree's `backend/`, run
  `<main>/backend/.venv/bin/pytest` and the other tools the same way, after checking that
  `import app` resolves to the worktree.
- **No attribution:** no `Co-Authored-By` line or any AI attribution in commits or PRs.

## Stacking the branches afterwards (lessons from round 1)

1. **Rebase in order.** Rebase each branch onto the one below it, in the stack order.
2. **Re-chain migrations.** Each new migration's `down_revision` (and its `Revises:` line) must
   point at the previous branch's revision. Fold that fix into the migration's own commit with a
   `fixup!` commit and `GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash <base>`.
3. **Keep both sides of simple conflicts.** `pytest.ini` markers (sort them by number), the README
   module list, route table and marker list, `docs/adr/README.md`, the `_register_modules` import
   list, and new sections at the end of `services.py`, `schemas.py` and `routes.py` all conflict
   because two branches added lines in the same place.
4. **Watch for conflicts git can't see.** In round 1:
   - One branch still called a private helper that another branch had moved to `app/common`.
     Lint caught it.
   - Tests submitted as an organiser with no organisation after SCRUM-66 made that a 403. The
     tests caught it.
   - Two branches made the same `WholeNumber` move; the files were identical, so git merged them
     cleanly.
5. **Check every commit, not only the tip.** Check out each commit in a scratch worktree and run
   ruff check, ruff format --check and pytest. Then, at each branch tip, run
   `diff-cover coverage.xml --compare-branch=<branch below>`.
6. **Run the migration chain on a throwaway Postgres:**
   ```bash
   docker run -d --rm --name pg-check -e POSTGRES_USER=cs -e POSTGRES_PASSWORD=cs -e POSTGRES_DB=cs -p 55439:5432 postgres:16-alpine
   DATABASE_URL=postgresql+psycopg2://cs:cs@localhost:55439/cs FLASK_APP=wsgi \
     flask db heads && flask db upgrade && flask db check && flask db downgrade base && flask db upgrade && flask db check
   docker stop pg-check
   ```
7. **Open the PRs bottom up,** each `--base` on the branch below. Add a "Stack" section to each
   description listing the whole stack, marking this PR, and stating the merge order.
