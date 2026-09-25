---
name: review-checklist
description: Review code in this repo against its Jira story (acceptance criteria pulled live from the SCRUM project via the Atlassian MCP server), the team's checklist (docs/code-review-checklist.md) and the Python conventions (backend/CONVENTIONS.md), with extra weight on readability over cleverness. Use before declaring any code change done (self-review of your own work — required by CLAUDE.md's definition of done), when asked to review a PR, branch or diff, or when the user types /review-checklist. Accepts an optional target — a PR number, a branch name, or a path; defaults to the current branch plus uncommitted changes.
---

# Review checklist

Review a change the way a careful teammate on this project would: check it does what the Jira
story asks, run the CI checks, then walk the human checklist, treating readability as a real
finding rather than a nit.

## 1. Work out what to review

- **No argument** (the usual self-review case): everything on this branch that isn't on
  `main`, plus uncommitted work.
  ```bash
  git diff main...HEAD --stat && git diff HEAD --stat
  git diff main...HEAD && git diff HEAD
  ```
- **PR number:** `gh pr diff <n>` and `gh pr view <n>` (title, description).
- **Branch:** `git diff main...<branch>`.
- **Path:** review that file or folder as it stands.

Read each changed file **in full**, not just the diff hunks, and open the callers of anything
whose signature or behaviour changed. Bugs hide in the context the hunk doesn't show.

## 2. Pull the story from Jira

**Find the story key** (`SCRUM-<n>`), looking in this order: the PR title, the branch name, the
commit subjects (`git log main..HEAD --format=%s`), and the `pytestmark` markers in changed
tests (`scrum_19` → `SCRUM-19`). If more than one key turns up, review against each one. If
none does, ask the user which story this is. Don't guess.

**Fetch it** with the Atlassian MCP tools (`mcp__atlassian__*`; load them with ToolSearch if
they're deferred):

- Site / `cloudId`: `smu-team-uu78imq6.atlassian.net`. If the hostname is rejected, use the
  UUID `b7aa222c-d70e-43da-b9a6-16d93f2b7663`.
- `getJiraIssue` with `responseContentFormat: "markdown"` and
  `fields: ["summary", "description", "status", "issuetype", "parent", "subtasks", "issuelinks",
  "comment", "customfield_10074"]`.

Take these from the issue:

| Where | What it gives you |
|---|---|
| `description`, the bullets under **Acceptance criteria** | The ACs. Number them AC1, AC2, … in the order listed; the code and tests already refer to them that way. |
| `comment` | Clarifications agreed after the story was written. Where they narrow or change an AC, they win. |
| `subtasks` named like "Ask customer" | Open questions. If one is still unresolved and the change depends on the answer, there must be an ADR in `docs/adr/` recording the interim decision. |
| `customfield_10074` (Roles) | The persona(s) the story is for. Cross-check against the `@requires_role(...)` allow-list. |
| `parent` | The epic. Context only (e.g. `EVT - Event Request Lifecycle`). |
| `issuelinks` | Stories this one blocks or depends on. Check the change doesn't quietly implement a linked story's scope. |

**Read-only.** Never transition, edit, comment on or log work against an issue from this skill,
even though the connection allows writes. If the user wants Jira updated, they'll ask
separately.

**If Jira can't be reached** (tools missing, not logged in, or an error), fall back to
`backend/STORIES.md` and the PR description. Say so at the top of the report, because the
local copy may be out of date. Don't pass the AC check silently.

Then read any ADR in `docs/adr/` that names this story.

## 3. Run the automated checks

From `backend/` (activate `.venv` if it exists):

```bash
ruff check .
ruff format --check .
pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=90
diff-cover coverage.xml --compare-branch=origin/main --fail-under=100
```

For a PR, compare against its base branch instead of `origin/main` if it differs. CI runs the
same `diff-cover` check, so a failure here will fail the PR.

If the change touches `models.py` or `migrations/`, also run `flask db heads` (must be exactly
one) and, **only if Postgres is running**, `flask db check`. If a check can't run (no venv, no
DB), say so in the report — never report it as passing.

Don't repeat what these tools report as hand-review findings; list their failures once in the
report.

**Coverage of changed code must be 100%, lines and branches.** `diff-cover` lists the changed
lines left uncovered. It can't see branches, so also match the `a->b` entries in pytest's
`Missing` column (a branch not taken) against the lines this change added or modified. For
each miss in changed code:

- There's a `# pragma: no cover - <reason>` and the reason holds up → list it under
  **Coverage gaps** in the report. (A docstring note alone doesn't exclude a line, so
  `diff-cover` and CI still count it as a miss.)
- There's no reason, or the reason doesn't hold (it could be unit-tested) → **must** finding.

Misses in code this change didn't touch aren't findings.

## 4. Check every acceptance criterion

Build a traceability table: one row per AC.

| AC | Jira text (short) | Implemented at | Tested by | Verdict |
|---|---|---|---|---|
| AC3 | Cannot submit a proposed date in the past | `events/schemas.py:113` | `test_proposed_date_yesterday_is_rejected` | met (ADR-0001) |

- **Verdict** is one of: **met**, **partial**, **missing**, **untested**, or **diverges**.
  Use **diverges** when the code does something different from the AC's wording.
- An AC that is **missing**, **partial**, or **untested** is a **must** finding.
- A test only counts as **Tested by** if it isn't decorative. It must assert the observable
  outcome, and it must fail if the implementing line were deleted or its condition inverted.
  For the key lines, check this for real: break the line, run that test, then restore it.
  An AC whose only test is decorative is **untested**.
- **diverges** is a **must** unless an ADR or a Jira comment records the decision. Then it's met,
  with the ADR or comment cited in the row. For example, "end time earlier than start time"
  in Jira versus "must end strictly after it starts" in ADR-0002 is covered.
- Code that goes beyond every AC, with no ADR behind it, is a **should** finding (scope creep).
- If the allowed roles don't match the story's Roles field, that's a **question**. Roles names
  the persona, which isn't always the complete permission list.

## 5. Walk the checklist

Read `docs/code-review-checklist.md` and go through sections 1–11 against the change. Use
`backend/CONVENTIONS.md` (the § numbers) for the detail behind each item. Section 1's AC items
are already covered by step 4. Skip items that don't apply to this change — don't pad the
report with them.

Give **section 4 (readability)** a deliberate pass of its own, function by function. That
includes the three structural rules:

- **Helpers first:** is every helper defined above the functions that use it?
- **No repeated code:** does any block, condition or query appear twice, in the change or
  against existing code (search `app/common/` and the module)? Are there near-identical tests
  that should be one `parametrize`?
- **Fewest arguments:** any parameter that's unused, only passed through, or a boolean flag?
  Any hidden input read from `g`, `request` or a global instead? Test seams (`session`,
  `today`, factories) are exempt.

Then the readability questions:

- Could someone who didn't write it follow it in one read?
- Is there a plainer way to write it: a loop instead of a dense comprehension, a named variable
  instead of an inline expression, an early return instead of nesting?
- Is anything clever — dynamic dispatch, metaprogramming, truthiness where `is None` is meant, a
  new pattern where an existing one would do?
- Does any comment explain *what* instead of *why*? That usually means the code should change.

When the change is your own work, be as strict as you would be with someone else's. If you
wrote it and it took effort to get right, it probably needs to be simpler for the next reader.

## 6. Classify each finding

- **must** — bug, security gap, broken module boundary, unsafe migration, an AC that is
  missing, partial, untested or diverges without an ADR, changed code left uncovered without
  a reason.
- **should** — readability problems, repeated code, helpers below their callers, surplus
  arguments, decorative tests (beyond those that leave an AC untested), other convention
  breaks, weak or missing edge-case tests, scope beyond the story.
- **nit** — minor preference. Keep these few.
- **question** — something you can't judge without the author's or product owner's intent.

Only report findings you've verified against the code. For each one give `file:line`, what's
wrong, a concrete failure case or the rule it breaks (e.g. `§7 module boundaries`, `AC3`), and
the fix.

## 7. Act on it

- **Reviewing someone else's change:** report only. Don't edit their code unless asked.
- **Self-review (your own change):** first confirm the tests were written before the code and
  seen failing; if they weren't, say so in the report. Then fix every **must** and **should**
  finding, re-run step 3,
  and re-check what you touched. Leave nits unless they're trivial. Fixes stay within the
  change's scope — anything outside it goes in the report as a follow-up, not into the diff.
  A **must** that needs a product decision (an AC you can't meet as written, an unresolved
  "Ask customer" subtask) isn't yours to settle: stop and ask the user.

## 8. Report

Keep it short:

1. **Story:** key, summary, status, and a link (`https://smu-team-uu78imq6.atlassian.net/browse/<KEY>`).
   Or "Jira unavailable — checked against STORIES.md".
2. **Acceptance criteria:** the traceability table from step 4.
3. **Checks:** each automated check with passed / failed / not run (and why).
4. **Coverage gaps:** every uncovered line or branch in changed code, with its reason. Say
   "none" if there are none.
5. **Findings:** grouped must → should → nit → question, each with `file:line`. For a
   self-review, mark each as fixed or left open with a reason.
6. **Verdict:** one line — ready, ready after the listed fixes, or not ready.

If there are no findings, say so plainly. Don't invent some to fill the report.
