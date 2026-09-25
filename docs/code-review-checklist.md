# Code review checklist

Use this for every PR you review, and on your own branch before you ask for review. Each item
links to the rule in [Python conventions](../backend/CONVENTIONS.md) (§ = section number).

Items are ordered by cost of getting wrong: a missed module boundary or migration bug hurts the
whole team; a slightly vague name hurts one reader. If time is short, review from the top.

## 0. Before reviewing — let the machines go first

Don't review by hand what CI already checks. Confirm these are green (or run them locally from
`backend/`), then skip to section 1.

- [ ] **PR title** is `type(SCRUM-<id>): summary`; only `ci`/`build` may drop the
      `(SCRUM-<id>)` (`pr-title.yml`)
- [ ] **Lint**: `ruff check .` — style, imports, docstrings present, bandit security rules,
      no `date.today()` / naive `datetime.now()`
- [ ] **Format**: `ruff format --check .`
- [ ] **Tests + coverage**: `pytest --cov=app` passes and coverage ≥ 90% overall (changed
      code needs 100% — checked by hand in section 10)
- [ ] **Migrations**: one Alembic head; `flask db check` clean; downgrade → upgrade replays
- [ ] **App boots**: `/health` smoke test passes

Mypy isn't in CI yet, so type hints are reviewed by hand in section 8.

## 1. Scope and traceability

- [ ] The PR does one story (or one clearly-scoped fix). Unrelated changes are split out.
- [ ] **Commits are layered** (§15): one logical change each, each passing lint and tests
      on its own, in dependency order, with no "WIP" or "fix previous commit" commits.
- [ ] Every acceptance criterion of the story is implemented and tested — check against the
      **Jira story** (the single source of truth for requirements), one AC at a
      time. Read its comments too: agreed clarifications live there.
- [ ] Open "Ask customer" subtasks on the story that this change depends on have an ADR
      recording the interim decision.
- [ ] Nothing beyond the story was added (no speculative options, abstractions or endpoints).
- [ ] Where the ACs were ambiguous, the decision is recorded as an ADR in `docs/adr/` and the
      index table is updated.
- [ ] New test modules set `pytestmark` to the story's marker, and the marker is declared in
      `pytest.ini`.
- [ ] `README.md` route table and `.env.example` are updated if the change affects them.

## 2. Architecture and module boundaries (§7)

- [ ] No module imports another module's `models`. Cross-module access goes through that
      module's `services.py` (or `auth.permissions` for roles).
- [ ] Cross-module foreign keys are DB-level `ForeignKey(...)` only — no `relationship()` to
      another module's model.
- [ ] Nothing in `app/common/` imports from `app/modules/`.
- [ ] Routes are thin: parse → call a service → serialise. No validation, queries or business
      rules in `routes.py`.
- [ ] Services don't touch `request` or `g`; the route passes in what they need.
- [ ] A new module has `register(app)` and is added to `_register_modules` in
      `app/__init__.py`.
- [ ] No reimplementation of something that already exists (`load_or_raise`, `local_today`,
      `resolve_session`, `invalid_token_response`, `role_value`,
      `error_response`, `normalise_email`, the role groups...).
- [ ] Service functions take `session` (and `today` / factories where relevant) as keyword-only
      arguments with production defaults.

## 3. Correctness

- [ ] Trace each AC through the code by hand with one valid input and one invalid input.
- [ ] Boundaries are right: `<` vs `<=`, today vs yesterday, 0 vs 1, empty string vs
      whitespace vs `None`, first vs last retry attempt.
- [ ] `None`/missing values are handled wherever the type says `| None`.
- [ ] Type coercions are explicit and safe (e.g. token identity `str` → `int(...)`).
- [ ] Every `commit()` that can fail is followed by `rollback()` on the failure path.
- [ ] Retries have a bound, and only retry errors that a retry can fix.
- [ ] Race conditions: a "check then insert" is backed by a DB constraint, and the
      `IntegrityError` is translated into the right `AppError`.
- [ ] List endpoints have a deterministic order (tie-breaker on `id`).

## 4. Readability — the one-read test (guiding principle)

Readable beats clever. Correct code that a teammate can't follow in one read is a **should**
finding, not a nit.

- [ ] Could a teammate who didn't write this understand each function in one read, without
      asking the author?
- [ ] The obvious version is used: plain loops and `if`s over dense comprehensions, nested
      conditional expressions or chained one-liners.
- [ ] Intermediate results have names; early returns instead of deep nesting.
- [ ] No tricks: metaprogramming, dynamic `getattr` dispatch, custom descriptors, operator
      overloading, or truthiness checks where `is None` / `== 0` is meant.
- [ ] Follows the patterns already in the codebase instead of inventing a new one.
- [ ] Functions do one thing; a long function is split where that makes it clearer (not into
      one-line helpers that force the reader to jump around).
- [ ] **Helpers first** (§2): every helper sits above the functions that use it, so the file
      reads top to bottom.
- [ ] **No repeated code** (§7): no block, condition or query appears twice — in tests either
      (use `parametrize` and fixtures). No helper created for a single "future" use.
- [ ] **As few arguments as possible** (§7): no unused or pass-through parameters, no
      boolean flags that switch behaviour, and no hidden inputs read from `g`/`request`/globals
      to avoid an argument. Test seams (`session`, `today`, factories) are exempt.
- [ ] No comment is needed to explain *what* a line does — if one is, the code is rewritten.

## 5. Security (§12)

- [ ] Every non-public route has `@requires_auth` or `@requires_role(...)`, and the allowed roles
      match the story — not wider.
- [ ] Roles come from `Role` / role groups, never string literals.
- [ ] The acting user comes from `g.current_user_id`, never from the request body or URL.
- [ ] Reads are scoped to what the caller may see (e.g. filtered by organiser).
- [ ] Input schemas don't declare server-controlled fields (`id`, `status`, `reference`,
      owner ids).
- [ ] Output schemas don't expose internal ids, password hashes or other users' data.
- [ ] Error messages don't reveal internals or enable enumeration (login failures are generic).
- [ ] No secrets, real credentials or `.env` files committed. New config comes from env vars and
      is added to `.env.example`.
- [ ] Security-relevant randomness uses `secrets`, not `random`.
- [ ] No SQL built with string formatting.
- [ ] Every `# noqa: S...` has a written justification that holds up.
- [ ] Nothing sensitive is logged (passwords, tokens, full request bodies).

## 6. Errors and validation (§8, §9)

- [ ] Failures raise an `AppError` subclass with the right status; routes never build error
      responses by hand.
- [ ] Exceptions are chained with `from exc` and caught as narrowly as possible.
- [ ] Every request body goes through a schema via `load_or_raise`.
- [ ] Cross-field rules use `@validates_schema` with `field_name=` so the error points at the
      right field.
- [ ] User-facing messages are clear, specific and consistent in tone with existing ones.
- [ ] Strict types: integers reject booleans, booleans accept only `true`/`false`, times reject
      offsets where relevant.

## 7. Database and migrations (§10)

- [ ] Every model change has a migration in this PR, and the migration was read, not just
      generated.
- [ ] File named `NNNN_<verb>_<thing>.py`, readable `revision` id, `down_revision` points at
      the current head on `main`, module docstring names the story.
- [ ] `downgrade()` fully reverses `upgrade()`, including dropping Postgres enum types.
- [ ] No merged migration was edited.
- [ ] Constraints and indexes follow the naming convention (`uq_`, `ck_`, `ix_`), and names
      that code refers to live in a module constant.
- [ ] Invariants are enforced in the DB as well as the schema (`nullable=False`, unique, check).
- [ ] Timestamp columns are `DateTime(timezone=True)`; enum columns store values via
      `values_callable`.
- [ ] Columns that get filtered on have an index.
- [ ] No N+1 query patterns (a query inside a loop over query results).

## 8. Types (§4)

- [ ] Every function, including tests and private helpers, has full parameter and return
      annotations.
- [ ] Modern syntax: `list[...]`, `X | None`, `collections.abc` types.
- [ ] `Any` only at genuinely dynamic boundaries.
- [ ] Nullable columns are `Mapped[T | None]`, and the annotation matches `nullable=`.
- [ ] Every `# type: ignore` has a specific error code and is actually needed.

## 9. Dates and time (§11)

- [ ] Business dates come from `local_today()`; instants use `datetime.now(timezone.utc)`.
- [ ] Logic that depends on "today" takes it as a parameter, and tests pin it.
- [ ] Date/time comparisons don't mix naive and aware values.

## 10. Tests (§14)

- [ ] Tests were written first, from the ACs. For a self-review: were they seen failing before
      the implementation existed?
- [ ] Every AC has at least one test, and the module docstring says which ACs/ADRs it covers.
- [ ] Rejection paths and boundaries are tested, not just the happy path.
- [ ] **No decorative tests:** each test asserts an observable outcome (value, error + status,
      saved fields, log line), states the expected value literally, and would fail if the key
      line were deleted or its condition inverted. Try it on the most important ones.
- [ ] **Full coverage of changed code:** `pytest --cov=app --cov-branch --cov-report=term-missing`
      shows no missed line or branch in the changed code, or each gap has a stated reason.
- [ ] Test names describe the behaviour in a sentence.
- [ ] Deterministic: no real clock, no real randomness, no sleeps, no dependence on test order.
- [ ] Side effects that matter are asserted (`add`, `commit`, `rollback` calls).
- [ ] Shared setup uses existing fixtures/factories, or adds a new one to `conftest.py`.
- [ ] Any new `# pragma: no cover` has a reason and really can't be unit-tested; every gap
      is listed with its reason in the PR description.

## 11. Naming, docs and style (§3, §5)

- [ ] Names follow the conventions table and use British spelling (`organiser`, `normalise`).
- [ ] Names say what a thing is in domain terms; no unexplained abbreviations.
- [ ] Docstrings follow Google style, give HTTP status in `Raises:`, and reference the story/ADR
      behind a rule.
- [ ] Comments explain *why*, not *what*. No stale or commented-out code.
- [ ] `TODO`s are real follow-ups (`# TODO:` / `# TODO(product):`), not unfinished work in this
      story.
- [ ] Logs use `connectsphere.<module>` loggers and `event_name key=value` with lazy `%`
      args.

## Leaving review comments

- Prefix comments so the author knows what's blocking:
  - **must:** — has to change before merge (bug, security, boundary, missing test for an AC).
  - **should:** — worth changing; author can push back with a reason.
  - **nit:** — minor preference; never blocks.
  - **question:** — you want to understand, not necessarily change.
- Point to the rule (`§7 module boundaries`) or a concrete failure case, rather than "I'd do
  it differently".
- If a convention here turns out to be wrong, fix the doc in its own PR rather than arguing it
  in every review.
