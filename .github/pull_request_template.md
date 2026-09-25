<!--
Title: a Conventional Commit naming the story, e.g. `feat(SCRUM-19): submit an event request`.
Delete any section that doesn't apply, but keep "Decisions made" and "Tickets to open"; write
"None" in them if that's true. See backend/CONVENTIONS.md §15 ("Pull request description").
-->

## Summary

<!-- SCRUM-<n> "<story title>". What this PR builds, in two or three sentences. Mention any migration. -->

## Acceptance criteria

<!-- One line per AC from the Jira story: done, partly done, or deferred (and to which story). -->

- **AC1 (…):** 

## Decisions made

<!--
Every call the ACs didn't settle, each with a link to its ADR. Split them so a reviewer knows
which ones are still open:
-->

**Agreed with the team or customer:**

- 

**Defaults to review:**

- 

## What to check

<!-- Where a reviewer should look hardest: risky code, behaviour changes to earlier stories, migrations. -->

- 

## Tickets to open

<!--
Follow-up work this PR found but doesn't do: tech debt, questions for the customer, gaps
another story must cover. One line each, saying which story it belongs to or that it needs a
new ticket. Leave them here, not only as a `# TODO` in the code.
-->

- 

## Testing

<!-- Lint, format and tests at every commit; diff-cover against the base; migration checks; any `# pragma: no cover` with its reason. -->

- [ ] Lint, format and tests pass at every commit.
- [ ] `diff-cover` against the base is 100%.

## Stack

<!-- Only for stacked PRs: list the whole stack, mark this PR, and say the base and the merge order. Delete otherwise. -->
