# CLAUDE.md

ConnectSphere — event planning and venue booking backend (IS212 scrum project). A Flask
**modularised monolith**: one app, split into self-contained modules under
`backend/app/modules/<name>/`. `README.md` has setup, the route table and the architecture note;
this file is the working rules.

## Guiding principle: readable over clever

Write the version a teammate who didn't write it can understand in one read. Plain loops over
dense comprehensions, named intermediate values, early returns, existing codebase patterns over
new ones, no tricks. Correct-but-hard-to-follow code is not done.

How code is written here (details in `backend/CONVENTIONS.md`):

- **Tests first.** Write the tests from the Jira ACs, watch them fail, then write the code.
- **No decorative tests.** Every test asserts an observable outcome and would go red if the
  code it covers broke.
- **Helpers first.** In every file, helpers sit above the functions that use them.
- **No repeated code.** Extract instead of copying, in tests too.
- **As few arguments as possible.** No unused, pass-through or boolean-flag parameters.

## Definition of done

Code work is not done until **all** of these hold. Do them in order, and don't tell the user
the work is finished before the last one:

1. **Tests were written first** and seen failing before the implementation existed.
2. `ruff check .`, `ruff format .` and
   `pytest --cov=app --cov-branch --cov-report=term-missing` pass (from `backend/`).
3. **Full coverage of changed code:** every line and branch you added or changed is covered,
   and any gap has a `# pragma: no cover - <reason>`. Check the lines with `diff-cover`
   (below), which CI also runs on every PR; check the branches yourself in the `Missing`
   column, since `diff-cover` can't see them.
4. **Self-review:** run the `review-checklist` skill on your own changes. Fix every **must** and
   **should** finding, then re-run step 2.
5. Report what the self-review found and fixed, anything left open (with why), and every
   coverage gap with its reason.

## Docs to read before working

| When | Read |
|---|---|
| Writing or changing Python | [backend/CONVENTIONS.md](backend/CONVENTIONS.md) — auto-loaded via `backend/CLAUDE.md` |
| Reviewing code (a PR, a branch, or your own work) | the `review-checklist` skill, which walks [docs/code-review-checklist.md](docs/code-review-checklist.md) |
| Implementing a story | The Jira story (`SCRUM-<n>` on `smu-team-uu78imq6.atlassian.net`, via the Atlassian MCP tools — read-only unless asked): ACs in the description, clarifications in comments. Then the relevant `docs/adr/` records. Jira is the only place requirements live; there is no local copy. |
| Acceptance criteria are ambiguous | `docs/adr/README.md` — record the decision as a new ADR |

## Commands

All from `backend/` with the venv active (`pip install -r requirements-dev.txt`).

```bash
ruff check .                  # lint (includes security, docstring and timezone rules)
ruff format .                 # format; CI runs `ruff format --check .`
pytest                        # unit tests — Postgres NOT needed, the DB is mocked
pytest -m scrum_19            # one story's tests
pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=xml   # CI floor: 90%
diff-cover coverage.xml --compare-branch=origin/main --fail-under=100     # changed lines: 100% (in a stack, compare with the branch below)
flask db migrate -m "..."     # autogenerate a migration — then review and rename it
flask db upgrade && flask db check   # apply, and confirm models match migrations
flask db heads                # must print exactly one head
```

## Architecture rules (do not break these)

- **Module boundaries.** A module never imports another module's `models`. It calls the other
  module's `services.py` functions (or imports `auth.permissions` role constants). Cross-module
  foreign keys exist at the DB level only — no ORM relationship across modules.
- **`app/common/` never imports from `app/modules/`.** The dependency arrow only points inward.
- **Layers inside a module:** `routes.py` (thin: parse JSON → call service → serialise) →
  `services.py` (business logic, the module's public API) → `schemas.py` (marshmallow
  validation) / `models.py` (SQLAlchemy). New modules expose `register(app)` and are added in
  `app/__init__.py::_register_modules`.
- **Errors:** services raise `AppError` subclasses from `app.common.errors`; routes never build
  error responses. Every error body is `{"error", "message", "details?"}`.
- **Auth:** protect routes with `@requires_auth` / `@requires_role(Role.X)` from
  `app.common.decorators`. Never spell role strings by hand — use `Role` and the role groups in
  `app.modules.auth.permissions`.
- **Dates:** never `date.today()` or naive `datetime.now()` (ruff DTZ blocks them). Business dates
  come from `app.common.clock.local_today()` (ADR-0001), and validation takes `today` as a
  parameter so tests can pin it.
- **Testability:** service functions take keyword-only `session: Session | None = None` (and
  other collaborators like `today`) so tests inject mocks.

## Gotchas

- Autogenerated migrations need review: rename to `NNNN_<verb>_<thing>.py`, set a readable
  `revision` id, and make `downgrade()` drop any Postgres enum type it created
  (`drop_table` leaves it behind; CI replays downgrade → upgrade).
- Two branches each adding a migration produce two Alembic heads after merge — CI fails. Rebase
  and fix `down_revision`, or `flask db merge`.
- The unit suite has no Flask test client and no real DB. Route/decorator tests use
  `app.test_request_context(...)` and call the view directly; see `tests/conftest.py`.
- Every test module sets `pytestmark = pytest.mark.<story_marker>`; new markers must be declared
  in `pytest.ini` (`--strict-markers`).
- Spelling in code and API is British (`organiser`, `normalise`, `serialise`) — match it.
- `frontend/` is a placeholder; the framework is not decided. Do not scaffold it.

## Git and PRs

- PR titles are Conventional Commits, enforced by `.github/workflows/pr-title.yml`. Use the
  same format for commit subjects.
  - `feat fix docs chore refactor test perf style revert` **must** name the story:
    `feat(SCRUM-19): submit an event request`.
  - Only `ci` and `build` (pipelines, dependencies, Dependabot) may leave it out:
    `ci: cache pip downloads`. If they give a scope, it must be a story (`ci(SCRUM-5): ...`),
    never a free-form one like `build(deps)`.
- **Layered commits** (`backend/CONVENTIONS.md` §15): one logical change per commit, each
  passing lint and tests on its own, stacked in dependency order. Merge with **Rebase and
  merge**, never squash.
- CI (`.github/workflows/ci.yml`) runs on every PR whatever branch it targets, so a stacked PR
  gets its checks at once; `diff-cover` compares with the PR's own base, and the overall and
  changed-lines coverage figures are posted as one comment on the PR, updated on each push.
- **PR description** (`backend/CONVENTIONS.md` §15): fill in `.github/pull_request_template.md`.
  "Decisions made" lists every call the ACs didn't settle, linked to its ADR and split into
  agreed vs defaults to review. "Tickets to open" lists follow-ups for the team to raise in Jira.
  Write "None" rather than deleting either one.
- Branch off `main`; never commit `backend/.env` or real secrets.
