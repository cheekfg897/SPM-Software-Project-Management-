# ADR-0127: Coverage means 100% of lines and branches, on unit tests alone, and CI fails below it

- **Status:** Proposed
- **Date:** 2026-11-01
- **Story:** SCRUM-40 Report test coverage on every build (AC3: "the agreed threshold")

## Context
The course rubric and FAQ ask for 100% coverage, or a stated reason where that isn't possible.
CI held the whole codebase to 90% and changed lines to 100%. It had no check on branches, and
its figure counted the e2e journeys as well as the unit tests.

So a few old lines and branches on `main` were never run by a unit test: the error handlers,
`/health`, three auth routes and one way of finding the database on the backend, two branches
on the frontend. Every one could be reached by a unit test, once someone looked. Nothing in the
pipeline had made anyone look.

## Decision
1. **Coverage is measured on unit tests alone.** On the backend that's `pytest -m "not e2e"`, on
   the frontend `npm run test:coverage`. The e2e journeys, the integration tests and Playwright
   all still run, but a line only they reach counts as uncovered, because a unit test is the
   one that names what broke.
2. **The floor is 100%, of lines and branches.** `--cov-fail-under=100` with `--cov-branch` on
   the backend, and all four thresholds in `vite.config.ts` on the frontend.
3. **A gap needs a stated reason.** `# pragma: no cover - <reason>` or
   `/* v8 ignore next -- <reason> */`, and only where a unit test really can't reach the line.
4. **`diff-cover` stays,** because it names the lines a pull request left uncovered, in the
   report posted on that pull request.

## Consequences
- A pull request that leaves any line or branch uncovered fails CI, including one that only
  moved old code. That's the point, but it does end the "not my line" escape.
- The figure must hold in CI's environment, not only on a laptop. CI sets `DATABASE_URL`, which
  hid a path a laptop runs, so tests that depend on the environment set it themselves.
- Only the jobs named in `main`'s branch protection can block a merge, so the frontend's floor
  blocks one only once its job is a required check.
- Every open pull request has to reach 100% before it merges, so this has to land after the
  branches that close today's gaps, and open branches need rebasing onto it.
- 100% only shows that a line ran, not that a test would notice it breaking. The
  no-decorative-tests rule and mutation checks in review still do that work.

## Revisit when
A line can't be reached by a unit test and the exclusions start to pile up, or the floor starts
pushing people to write tests only for the number.
