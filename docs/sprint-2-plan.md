# Sprint 2 plan: the remaining tickets as stacked rounds

This is a working plan for finishing Sprint 2 in parallel batches. It is written as a handoff so a
new session can pick it up. Requirements still live only in Jira (`SCRUM-<n>` on
`smu-team-uu78imq6.atlassian.net`), so this file lists order and dependencies, not ACs. Read each
story's ACs and comments in Jira before planning it.

Written 2026-09-25, when `main` was at `bf4652c`. Updated 2026-09-26 after rounds 2 and 3.

Sprint 2 ends on 2026-10-04. Sprint 3 runs from 2026-10-04 to 2026-10-18.

## Where things stand

Rounds 1 to 3 are one stack of twelve PRs. Each PR is based on the one listed above it, and
nothing has merged yet. Every PR has keene-ng-2024 as a reviewer.

| # | PR | Branch | Migration | ADR |
|---|---|---|---|---|
| 1 | #17 SCRUM-22 event status model | `feat/SCRUM-22-event-status-model` (base `main`) | 0006 | 0012 |
| 2 | #18 SCRUM-66 client organisations | `feat/SCRUM-66-client-organisations` | 0007 | 0013 |
| 3 | #19 SCRUM-27 equipment catalogue | `feat/SCRUM-27-equipment-catalogue` | 0008 | 0014 |
| 4 | #20 SCRUM-28 notifications | `feat/SCRUM-28-notifications` | 0009 | 0015 |
| 5 | #21 SCRUM-34 block a venue | `feat/SCRUM-34-block-venue` | none | 0016 |
| 6 | #22 SCRUM-36 venue suitability | `feat/SCRUM-36-venue-suitability` | none | 0017 |
| 7 | #24 SCRUM-30 assign a coordinator | `feat/SCRUM-30-assign-coordinator` | 0010 | 0018 |
| 8 | #25 SCRUM-37 event equipment | `feat/SCRUM-37-event-equipment` | 0011 | 0019 |
| 9 | #26 SCRUM-5/40 CI on every PR | `ci/SCRUM-5-stacked-pr-checks` | none | none |
| 10 | #28 SCRUM-7 organisation's events | `feat/SCRUM-7-organisation-events` | none | 0020 |
| 11 | #29 SCRUM-87 reassign a coordinator | `feat/SCRUM-87-reassign-coordinator` | 0012 | 0021 |
| 12 | #30 SCRUM-38 equipment awaiting action | `feat/SCRUM-38-equipment-awaiting-action` | 0013 | 0022 |

#27 (SCRUM-5, the PR description template) is separate, based on `main`.

- **Next free numbers:** migration **0014**, ADR **0023**.
- **Checks:** every commit passes lint, format and tests on its own. `diff-cover` is 100% for
  each PR against the branch below it. The migration chain 0001 to 0013 was checked on
  Postgres 16: one head, upgrade, `db check`, downgrade to base, upgrade.
- **CI:** since #26, CI runs on every PR whatever its base. It measures `diff-cover` against the
  PR's own base and posts the coverage figures as a comment on the PR.
- **Merging:** bottom up, with **Rebase and merge**. Automatic branch deletion is **off** in
  this repo, so delete each merged branch by hand. GitHub then retargets the next PR to `main`.
- **Review is the bottleneck.** Twelve stacked PRs are waiting for review. A change requested
  low in the stack means rebasing everything above it, so get #17 to #22 reviewed before the
  stack grows much taller.

This file sits on its own branch, `docs/sprint-2-plan`, on top of #22. **Don't build on this
branch.** Start each new branch from `feat/SCRUM-38-equipment-awaiting-action`, the top of the
stack, or from `main` once the stack has merged.

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
- **Event statuses (ADR-0012):** `draft`, `submitted`, `under_review`, `confirmed`, `completed`,
  `cancelled`, `rejected`.
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

## What's left in Sprint 2

Done: 22, 66, 27, 28, 34, 36, 30, 37, 5/40, 7, 87, 38 (all in review).

### Can start now

| Ticket | Needs | Notes |
|---|---|---|
| SCRUM-20 Save and resume drafts | 22, 7, 30 | Other organisers in the same organisation mustn't see a draft: narrow `_visible_to_organiser`. A draft is assigned only when submitted. Saving a draft sends no notification. |
| SCRUM-33 Edit event info with change history | 30 | Four of its five ACs can be built now. AC2 marks a change significant and "raises a reassessment of the affected arrangements": equipment lines exist, so reassess those, but venue bookings don't exist until SCRUM-42 (Sprint 3). Record that gap in an ADR, or ask the PO to split the venue part into a Sprint 3 ticket. It also has the `needs-customer-clarification` label, with no comment saying what's unclear; ask the team first. |
| SCRUM-24 See the events my role is involved in | 7, 30 | Only the organiser and coordinator views can be built now. The Venue Staff, Technical Support and attendee views wait on 42, 46 and 52. It may also be where unassigned requests get picked up (see ADR-0018 and ADR-0021). |
| SCRUM-88 Internal staff roles can self-register | none | A security bug in public registration. It's related to organisers registering under a guessed organisation id (ADR-0013), which #28 now lets them use to read that organisation's events. It needs a design decision first, e.g. whether an internal user must create or approve accounts. |

### After SCRUM-33

| Ticket | Needs | Notes |
|---|---|---|
| SCRUM-68 Mark an event completed | 30, 33 | "Can no longer be edited" relies on 33. Nothing sets Confirmed until SCRUM-49 (Sprint 3), so tests set the status directly. |

### Blocked on the "Approved" decision (SCRUM-23)

| Ticket | Needs | Notes |
|---|---|---|
| SCRUM-31 Review and decide a request | 30, decision | It uses an "Approved" status that isn't among ADR-0012's seven. Record decisions in the event history. |
| SCRUM-32 Ask the organiser for clarification | 31 | Uses the `under_review` status. |
| SCRUM-39 Notifications for review decisions | 30, 31, 32, 87 | 30, 87 and 31/32 send their own notifications. 39 fills the gaps: telling the organiser a coordinator was assigned or reassigned. |
| SCRUM-41 End-to-end test from request to approval | 20, 30, 31, 32 | draft → submit → assign → clarify → resubmit → approve. |

Four of the nine tickets left wait on this one answer. If the customer can't answer soon, decide it
in an ADR and build SCRUM-31 on that assumption.

### Sprint 3, not this sprint

- **SCRUM-42** (request a venue for an event) and **SCRUM-46** (reserve equipment).
- **SCRUM-84** needs venue bookings (SCRUM-42).
- **SCRUM-85** needs equipment reservations (SCRUM-46).

## Suggested round 4

**88 → 20 → 33 → 24**, each on the one before, on top of #30.

- 88 goes first because it's a security fix, and it only touches the auth module.
- 20, 33 and 24 all touch the events module. In this order each builds on the scope and history
  code the one before it leaves.
- Reserve, in that order: migrations 0014 to 0016 and ADRs 0023 to 0026, each used only if needed.
  Renumber unused ones away when stacking (see below).
- Settle SCRUM-88's design decision, and ask what SCRUM-33's clarification label is about, before
  launching.

## Decisions that unblock the most

1. **"Approved" status:** is it an eighth status, or does approval move a request to
   `under_review`/Planning? Blocks SCRUM-31, and through it 32, 39 and 41 (see ADR-0012 and
   SCRUM-23). **Open.**
2. **Coordinator assignment rule:** **settled**. The least-loaded coordinator gets the request
   (ADR-0018).
3. **SCRUM-36 input:** should the suitability check take an event id instead of requirements
   (ADR-0017)? Needed by SCRUM-42. **Open.**
4. **Registration security (SCRUM-88):** anyone can self-register, including under a guessed
   organisation id (ADR-0013). SCRUM-7 shipped anyway (#28 carries a warning), so this is now the
   most urgent. **Open.**
5. **Role limits:** should routes follow each story's Roles field? SCRUM-34's field lists Event
   Coordinator, but its routes are Venue Staff only. **Open.**
6. **SCRUM-33 AC2's venue half:** build it with SCRUM-42 later, or split it into its own ticket?
   **Open.**

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

## Stacking the branches afterwards (lessons from rounds 1 to 3)

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
