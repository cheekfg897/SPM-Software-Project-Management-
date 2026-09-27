# Python conventions

How we write Python in `backend/`. Most of this is already what the code does; the doc exists
so new code keeps doing it. When the code and this doc disagree, raise it in the PR and fix
whichever is wrong.

**Enforced by tooling** (don't spend review time on these — CI fails them):
`ruff check` (rules in `backend/ruff.toml`) and `ruff format --check`. Everything else here is
checked by people, using [the review checklist](../docs/code-review-checklist.md).

Contents: [Tooling](#1-tooling) · [Formatting](#2-formatting-and-layout) ·
[Naming](#3-naming) · [Type hints](#4-type-hints) · [Docstrings and comments](#5-docstrings-and-comments) ·
[Imports](#6-imports) · [Module structure](#7-module-structure) · [Errors](#8-errors) ·
[Validation](#9-validation-marshmallow) · [Database](#10-database-models-and-migrations) ·
[Dates and time](#11-dates-and-time) · [Security](#12-security) · [Logging](#13-logging) ·
[Testing](#14-testing) · [Commits](#15-commits)

---

## Guiding principle: readable over clever

The reader is a teammate who didn't write the code, reading it once, probably while
debugging something else. Optimise for them, not for brevity or elegance.

- **Write the obvious version.** A plain `for` loop with an `if` beats a nested comprehension
  with a conditional expression. Two clear lines beat one dense line.
- **Name intermediate results.** `ends = datetime.combine(end_date, end_time)` reads better than
  inlining it into a comparison.
- **Return early** instead of nesting `if`/`else` several levels deep.
- **No tricks:** no metaprogramming, dynamic `getattr` dispatch, custom descriptors, operator
  overloading or clever use of truthiness where a direct check would do
  (`if value is None`, not `if not value`, when `0` or `""` are valid).
- **Use the patterns already in the codebase** before inventing a better one. Consistent and
  boring beats locally optimal.
- **If it needs a comment to explain *what* it does, rewrite it.** Comments are for *why*.
- A reviewer asking "what does this do?" is a finding, even if the code is correct.

Where readability and a *style* preference below pull in different directions, readability
wins; say so in the PR. Correctness, security and architecture rules are not negotiable this
way.

---

## 1. Tooling

| Tool | Purpose | Run |
|---|---|---|
| Python 3.12 | Version pinned in `backend/.python-version` | — |
| ruff | Lint + format + import sort + security (bandit `S`) + docstrings (`D`) | `ruff check .` / `ruff format .` |
| pytest + pytest-cov | Unit tests, 90% coverage gate in CI | `pytest --cov=app` |
| Flask-Migrate (Alembic) | Schema migrations | `flask db ...` |
| pip-audit | Dependency CVEs (advisory in CI) | `pip-audit -r requirements.txt` |

- Dependencies are **pinned exactly** (`==`). Runtime deps go in `requirements.txt`, dev-only
  tools in `requirements-dev.txt`. Group them under a comment saying what they're for.
- Don't disable a ruff rule globally to get one line through. Use a line-level
  `# noqa: <CODE>` with a reason, or a `per-file-ignores` entry with a comment explaining why.

## 2. Formatting and layout

- `ruff format` owns formatting (Black-compatible). Don't hand-format against it.
- Code lines ≤ **100** characters; docstrings and comments ≤ **88** (ruff `W505`).
- Double quotes. Trailing commas in multi-line calls and literals (the formatter keeps them
  exploded one-per-line).
- Two blank lines between top-level definitions. Inside long test files, group tests under a
  banner comment naming the AC or ADR they cover:

  ```python
  # --------------------------------------------------------------------------
  # ADR-0004 — reference collisions are retried, other failures are not
  # --------------------------------------------------------------------------
  ```

- Inside a class, a short divider comment may group related methods
  (`# -- credentials ---`), as in `auth/models.py`.

**File order — helpers first.** A file reads top to bottom, and every name is defined before
the code that uses it:

1. Module docstring, then imports.
2. Constants and module-level config (`logger`, `REFERENCE_PREFIX`, ...).
3. Small types the helpers need (error classes, dataclasses).
4. **Private helpers** (`_role_value`, `_configure_logging`, ...), each above the first function that
   calls it.
5. The public functions or classes — the module's real job — built from those helpers.

Test files follow the same order: constants, then fakes and helpers (`_integrity_error`,
`_references`), then the tests. Inside a class, put a helper method above the methods that use
it where the framework allows (marshmallow fields always come first).

## 3. Naming

**General (PEP 8):**

| Thing | Style | Example |
|---|---|---|
| Module / package | `snake_case` | `validation.py`, `modules/events/` |
| Function, method, variable | `snake_case` | `submit_event_request`, `event_request` |
| Class | `PascalCase` | `EventRequest`, `SubmitEventRequestSchema` |
| Constant | `UPPER_SNAKE_CASE` | `MAX_REFERENCE_ATTEMPTS`, `ROLE_CLAIM` |
| Private (module- or class-internal) | leading `_` | `_role_value()`, `_event_request_schema` |
| Type variable | Single capital or `PascalCase` | `F = TypeVar("F", bound=Callable[..., Any])` |

**Spelling:** British English in identifiers, messages and docs — `organiser`, `normalise`,
`serialise`, `organisation`. The domain uses these words everywhere; mixing spellings breaks
search.

**Names should say what, not how.** Prefer the full domain word (`event_request`, not `er` or
`req`). Short names are fine for tiny scopes (`exc`, `stmt`, `sess`, comprehension variables).

**Project-specific patterns:**

| Thing | Pattern | Example |
|---|---|---|
| Service functions | verb + noun, reads as a sentence | `get_user_by_id`, `list_event_requests_for_organiser` |
| Predicates | `is_` / `has_` prefix, return `bool` | `is_internal_role`, `is_reference_collision` |
| Route view functions | what the caller does | `submit_request`, `list_my_requests` |
| Input schema | `<Action><Entity>Schema` | `SubmitEventRequestSchema`, `RegisterSchema` |
| Output schema | `<Entity>Schema` | `EventRequestSchema`, `UserSchema` |
| Error classes | `<What>Error`, subclass of `AppError` | `ReferenceGenerationError` |
| `error_code` values | `snake_case` | `"reference_generation_failed"` |
| Enum | `PascalCase` class, `UPPER_SNAKE` members, `snake_case` values | `Role.EVENT_ORGANISER = "event_organiser"` |
| Blueprint | module name, `url_prefix="/api/<module>"` | `Blueprint("events", __name__, url_prefix="/api/events")` |
| URL paths | kebab-case; collections are plural nouns | `/api/events/requests`, `/api/auth/internal-only` |
| JSON keys | `snake_case` | `expected_attendance` |
| Logger | `connectsphere.<module>` | `logging.getLogger("connectsphere.events")` |
| Config keys | `UPPER_SNAKE`, same name as the env var | `APP_TIMEZONE` |

**Database names:**

| Thing | Pattern | Example |
|---|---|---|
| Table | plural `snake_case` | `users`, `event_requests` |
| Postgres enum type | `<entity>_<field>` | `user_role`, `event_request_status` |
| Unique constraint | `uq_<table>_<column>` | `uq_event_requests_reference` |
| Check constraint | `ck_<table>_<rule>` | `ck_event_requests_expected_attendance_min` |
| Index | `ix_<table>_<column>` (via `op.f`) | `ix_event_requests_organiser_id` |
| Migration file | `NNNN_<verb>_<thing>.py` | `0002_create_event_requests_table.py` |
| Migration `revision` | `NNNN_<short_name>` | `"0002_create_event_requests"` |

Name a constraint whenever code needs to refer to it, and keep that name in a module constant
(`REFERENCE_UNIQUE_CONSTRAINT`) instead of repeating the string.

## 4. Type hints

Every function — including tests, fixtures and private helpers — is fully annotated. The code
is written to pass **mypy**; no type checker runs in CI yet, so this is enforced in review.

**Rules:**

- Start every module with `from __future__ import annotations` (after the module docstring).
- Annotate every parameter and the return type, including `-> None`.
- Modern syntax only (Python 3.12, and ruff `UP` flags the old forms):
  - `list[str]`, `dict[str, Any]`, `tuple[Response, int]` — not `List`, `Dict`, `Tuple`.
  - `X | None` — not `Optional[X]`. `int | str` — not `Union[int, str]`.
  - Abstract types from `collections.abc`: `Callable`, `Iterable`, `Iterator`, `Mapping`.
- Keep `TypeVar` explicit (`F = TypeVar("F", ...)`); don't use PEP 695 `def f[T]()` syntax
  (ruff `UP047` is ignored on purpose — it's unfamiliar to most of the team).
- **Accept broad, return narrow.** Take `Mapping[str, Any]` / `Iterable[...]` for inputs;
  return concrete `list[...]` / `dict[...]`.
- Untrusted input (a decoded JSON body) is `Mapping[str, Any] | None` until a schema has
  validated it.
- Use `Any` only at genuinely dynamic boundaries (JSON payloads, JWT claims, `*args/**kwargs`
  in decorators, marshmallow hook signatures). Don't use it to avoid thinking about a type.
- SQLAlchemy columns use 2.0 typed mappings: `name: Mapped[str] = mapped_column(...)`, and
  `Mapped[str | None]` for nullable columns.
- Mutable class-level attributes that aren't instance fields are `ClassVar[...]`
  (e.g. `JWT_TOKEN_LOCATION: ClassVar[list[str]]` in `config.py`).
- Fixed groups of constants are `frozenset[...]`, not `list` or `set` (`INTERNAL_ROLES`).
- Small immutable result records are `@dataclass(frozen=True)` (`AuthResult`).
- String enums subclass `(str, enum.Enum)` so members compare equal to, and serialise as, their
  value.
- Silencing the checker: always `# type: ignore[<error-code>]` with the specific code, never a
  bare `# type: ignore`. Current accepted uses: `db.Model` base (`name-defined`), decorator
  wrappers returned as `F` (`return-value`), and attributes attached to functions
  (`attr-defined`).

## 5. Docstrings and comments

ruff's `D` rules require a docstring on every public module, class and function (tests and
Alembic `upgrade/downgrade` are exempt).

**Docstrings — Google style:**

```python
def submit_event_request(
    organiser_id: int | str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> EventRequest:
    """Submit a new event request on behalf of an organiser (SCRUM-19).

    Validates the payload (AC1-AC4), then saves it with status ``submitted``.

    Args:
        organiser_id: The caller's user id, taken from their token.
        payload: Decoded JSON body.
        session: Database session; defaults to ``db.session``.

    Returns:
        The saved :class:`EventRequest`.

    Raises:
        ValidationError: 400 — payload invalid (details per field).
    """
```

- First line: one sentence, imperative or descriptive, ending in a period.
- `Args:` / `Returns:` / `Raises:` when they add information. A one-liner is fine for a
  function whose signature says it all.
- In `Raises:`, give the HTTP status for `AppError` subclasses (`ConflictError: 409 — ...`).
- Reference the story, acceptance criterion or ADR a rule comes from (`(SCRUM-19 AC5)`,
  `(ADR-0002)`). That's how a reader finds out *why*.
- Inline code in docstrings uses double backticks (``` ``submitted`` ```); cross-references use
  Sphinx roles (`:func:`, `:class:`, `:mod:`, `:data:`).
- Module docstrings say what the module is responsible for and any rule a caller must know
  (e.g. "Other modules must **not** import these directly").
- Document a module-level constant or model column with a `#:` comment on the line above it.

**Comments** explain *why* — the constraint, the trade-off, the edge case — not what the next
line does. Good examples already in the code: why login burns a dummy hash check, why
`values_callable` is set on enum columns, why `registration_required` uses strict truthy sets.

- `# TODO:` for known follow-up work; `# TODO(product):` when it needs a customer/PO decision.
- `# pragma: no cover - <reason>` only for branches that genuinely can't run in unit tests
  (misconfiguration guards, debugging aids, HTTP-only handlers). Always give the reason.
- `# noqa: <CODE>` needs a nearby comment explaining why the rule doesn't apply.

## 6. Imports

- ruff's isort (`I`) orders them: stdlib, third-party, then first-party (`app...`), with
  `combine-as-imports`.
- Absolute imports only: `from app.common.errors import AppError`, not relative imports.
- Import names, not modules, for app code (`from app.modules.events.services import ...`).
- Alias on name clashes, as the code does for marshmallow:
  `from marshmallow import ValidationError as MarshmallowValidationError`.
- `register(app)` imports its module's `routes` **inside** the function to avoid a circular
  import at app-factory time. Don't move it to the top.
- No wildcard imports.

## 7. Module structure

Each feature lives in `backend/app/modules/<name>/`:

| File | Owns | Must not |
|---|---|---|
| `__init__.py` | `register(app)`; docstring listing the module's public surface | contain logic |
| `routes.py` | Blueprint, auth decorators, parse request → call service → serialise | validate, query the DB, or build error responses |
| `services.py` | Business rules, DB reads/writes, module-specific `AppError` subclasses | touch `request` / `g` |
| `schemas.py` | Marshmallow input and output schemas | touch the DB |
| `models.py` | SQLAlchemy models and their constants | import another module's models |
| `permissions.py` | Role vocabulary (auth module only) | — |
| `commands.py` | Flask CLI commands: options → service → echo, registered in `register(app)` | validate, or touch the DB |

- **Boundaries:** modules talk through each other's `services.py` (and `auth.permissions` for
  roles). A foreign key to another module's table is a plain `ForeignKey("users.id")` — no
  `relationship()` and no import of that module's model.
- **`app/common/`** is for cross-cutting mechanisms (errors, auth decorators, clock,
  validation, health). It never imports from `app.modules`.
- **Before writing a helper, check `app/common/` and the module's `services.py`** — e.g.
  `load_or_raise`, `local_today`, `resolve_session`, `error_response`,
  `invalid_token_response`, `normalise_email` and `role_value` already exist.
- **Dependency injection for testability.** Service functions take collaborators as keyword-only
  arguments with production defaults:

  ```python
  def list_event_requests_for_organiser(
      organiser_id: int | str, *, session: Session | None = None
  ) -> list[EventRequest]:
      ...
      return list(resolve_session(session).scalars(stmt))
  ```

  Same pattern for `today: date | None = None` and factories like
  `reference_factory: Callable[[], str] = generate_reference`.
- Use keyword-only arguments (`*`) for anything optional or easy to mix up.
- The caller's identity comes from `g.current_user_id` (set by the auth decorators), never from
  the request body.
- Tunable business values (password length, timezone) live in `config.py`, read from
  environment variables, and are read via `current_app.config` with a module default when there
  is no app context.
- Keep functions small and single-purpose.

**No repeated code.** Logic exists in exactly one place.

- Before writing anything, search `app/common/` and the module for an existing helper.
- The moment you would copy a block, a condition or a query, extract it instead, and call it
  from both places. Used by one module → a private helper in that module. Used by two or
  more modules → `app/common/`.
- Tests too: repeated cases become one `@pytest.mark.parametrize` test, and repeated setup
  becomes a fixture or a `_helper` at the top of the file.
- Don't swing the other way: no helper for a single use "in case it's needed later". A helper
  exists because two real callers share it, or because it gives a hard-to-read block a name.

**As few arguments as possible.** Every parameter is something the caller must understand and
get right, so each one has to earn its place.

- A function takes only what it actually uses. No unused parameters and no parameters that are
  only passed through to another call.
- No boolean flag that switches behaviour (`save(draft=True)`): write two functions
  (`save_draft`, `submit`).
- More than three regular parameters usually means the function does too much. Split it, or
  pass the validated data as one value (as services pass the dict from `load_or_raise`).
- Don't cut arguments by reading hidden state instead. Reading `g`, `request` or a module global
  deep inside a service hides an input; that's worse than an argument.
- The exception is the keyword-only test seams above (`session`, `today`, factories). Production
  callers never pass them, so they don't add to what a caller has to know.

## 8. Errors

- Raise the `AppError` subclasses from `app.common.errors`: `ValidationError` (400),
  `AuthenticationError` (401), `AuthorizationError` (403), `NotFoundError` (404),
  `ConflictError` (409). Add a module-specific subclass in that module's `services.py` when none
  fit, setting `status_code` and `error_code`.
- `message` is shown to the client: make it clear, actionable and free of internals (no SQL,
  stack traces, ids of other users).
- Chain exceptions: `raise ConflictError("...") from exc`.
- Catch the narrowest exception you can handle (`IntegrityError`, not `Exception`). After a
  failed `commit()`, `rollback()` before retrying or re-raising.
- Don't catch an exception just to log and re-raise it; the global handler logs unexpected
  errors.
- Don't leak which part of a credential was wrong: every login failure uses
  `INVALID_CREDENTIALS_MESSAGE`.

## 9. Validation (marshmallow)

- Every request body goes through a schema via `load_or_raise(schema, payload)`, which turns
  marshmallow errors into a 400 with per-field `details`.
- Don't declare server-controlled fields (`id`, `status`, `reference`, `organiser_id`) on input
  schemas. Marshmallow's default `RAISE` then rejects them as unknown fields.
- Output schemas mark every field `dump_only=True` and leave out internal ids and secrets.
- Field-level rules go in `validate=` or `@validates("field")`; cross-field rules in
  `@validates_schema` (pass `field_name=` so the error lands on the right field); cleanup like
  trimming in `@post_load`.
- Be strict about types: `WholeNumber` rejects JSON booleans for integers; booleans use
  `truthy={True}, falsy={False}`.
- Put the user-facing message on the validator (`error="Expected attendance must be at least
  1."`) rather than relying on marshmallow's default wording.

## 10. Database, models and migrations

- Query with SQLAlchemy 2.0 `select(...)` and `session.scalars/scalar/get`. Never format values
  into SQL strings.
- Timestamps: `DateTime(timezone=True)`, with `created_at` / `updated_at` using
  `server_default=func.now()` (and `onupdate=func.now()` for `updated_at`).
- Enum columns store the **values**, not member names:
  `Enum(MyEnum, name="<entity>_<field>", values_callable=lambda e: [m.value for m in e])`.
- Enforce invariants in the database too (`nullable=False`, `UniqueConstraint`,
  `CheckConstraint`) — the DB is the real guarantee, especially against races.
- Every model change ships with a migration in the same PR:
  1. `flask db migrate -m "..."`, then **read the generated file**.
  2. Rename it to `NNNN_<verb>_<thing>.py`, set `revision` to `NNNN_<short_name>`, and write a
     module docstring naming the story.
  3. Make `downgrade()` fully reverse `upgrade()`, including dropping any Postgres enum type
     (`sa.Enum(name="...").drop(op.get_bind(), checkfirst=True)`).
  4. `flask db upgrade && flask db check`, and `flask db downgrade base && flask db upgrade`.
- Never edit a migration that has been merged to `main`; add a new one.
- Exactly one migration head. If your branch and `main` both added one, fix `down_revision`
  before merging.

## 11. Dates and time

Per ADR-0001, "today" means today in the business timezone (`APP_TIMEZONE`, default
`Asia/Singapore`), not on the server clock.

- Never call `date.today()` or `datetime.now()` without a tz — ruff `DTZ` fails the build.
- Business dates: `app.common.clock.local_today()`.
- Instants (timestamps, logs): `datetime.now(timezone.utc)`. We write `timezone.utc`, not
  `datetime.UTC` (ruff `UP017` is ignored on purpose).
- Logic that depends on "today" takes it as a parameter (`today: date | None = None`) so tests
  pin it.
- Event times are wall-clock times in the business timezone; reject inputs with an offset.

## 12. Security

- No secrets in code or git. Read them from the environment in `config.py`; `backend/.env` is
  gitignored, `.env.example` documents the keys.
- Random values that matter (tokens, references) come from `secrets`, never `random`.
- Passwords are hashed with Werkzeug (`set_password`) and never returned, logged or stored in
  plain text. Password fields are `load_only=True`.
- Every non-public route has `@requires_auth` or `@requires_role(...)`. Default to the most
  restrictive role set that satisfies the story.
- Scope data to the caller: an organiser's queries filter on the client organisation of the
  account named by `g.current_user_id` (ADR-0020), through one condition shared by the list
  and the detail view.
- Read request bodies with `request.get_json(silent=True)` and let the schema reject bad
  shapes.
- `# noqa: S...` (bandit) needs a written justification, like the test-only JWT secret in
  `TestingConfig`.

## 13. Logging

- Use a named logger per area: `logging.getLogger("connectsphere.<module>")`.
- Log as an event name followed by `key=value` pairs, with `%`-style lazy arguments (not
  f-strings):

  ```python
  logger.warning(
      "event_request_reference_collision reference=%s attempt=%d", reference, attempt
  )
  ```

- `warning` for handled-but-notable events (auth failures, retries), `exception` only in the
  global handler for unexpected errors, `info`/`debug` sparingly.
- Never log passwords, tokens, or full request bodies.

## 14. Testing

### Tests come first

Write the tests **before** the code they test:

1. **From the story.** Read the Jira ACs and write tests for each one: the happy path, every
   rejection, and the boundaries (the day before "today", attendance 0 and 1).
2. **Watch them fail.** Run them before writing the implementation. Each one must fail, and
   fail on its assertion rather than on a typo in the test (stub the new function's signature
   first if an `ImportError` would hide that). A test that passes before the code exists
   proves nothing.
3. **Write the least code that makes them pass**, then tidy it up with the tests still green.
4. **Measure coverage** with branches on:
   `pytest --cov=app --cov-branch --cov-report=term-missing`.

### No decorative tests

A test earns its place only if it would catch a real break. Every test must:

- Assert the observable outcome: the return value, the error raised and its status, the fields
  saved, the log line written. "It didn't raise" is not an assertion.
- Fail if the line it covers were deleted or its condition inverted. Check this: break the key
  line, see the test go red, then put it back.
- State the expected value literally (`== date(2026, 10, 15)`), not by re-running the same
  logic as the code under test.
- Not just check that a mock returned what the test itself configured it to return.
- Not exist only to raise the coverage number (trivial getters, framework behaviour).

### Full coverage of changed code

Every line **and branch** you add or change is covered by a non-decorative test. CI's 90% is
the floor for the whole codebase; for new code the bar is 100%.

CI enforces the **lines** on every pull request, whatever branch it targets: the *Changed lines
are fully covered* step runs `diff-cover` against the pull request's own base branch and fails
below 100%, and the overall and changed-lines figures are posted as a comment on the pull
request. It can't see branches, so an `if` tested only one way still passes CI; checking the
changed branches is on you and the reviewer. Run the same check before pushing, comparing with
your base (`origin/main`, or the branch below yours in a stack):

```bash
pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=xml
diff-cover coverage.xml --compare-branch=origin/main --fail-under=100
```

When a line genuinely can't be covered by a unit test, explain why rather than leave it
silently red:

- Mark it `# pragma: no cover - <reason>` (e.g. `- misconfiguration guard`, `- only reachable
  through the HTTP layer`). This is the only way to exclude a changed line: `diff-cover`
  ignores docstrings, so an uncovered line explained only in a docstring fails CI. (Some older
  code explains HTTP-only gaps in a docstring, as `register_error_handlers` does; add the
  pragma if you change one of those lines.)
- List every such gap, with its reason, in the PR description or the self-review report.

### The frontend's contract tests

The frontend reads the JSON these routes send. Its integration tests
(`frontend/src/integration/*.int.test.ts`) check that the two still agree, and CI runs them on
every pull request against that pull request's backend, so a change that breaks a response they
already check fails CI. CI can't see two things, so they're on the author of the backend change:

- **An endpoint or rule the frontend is waiting for.** A contract test that is still a
  placeholder (`it.todo('… (lands with SCRUM-66)')`) can't fail. The pull request that ships
  that endpoint or rule turns its placeholders into real tests.
- **The mock backend.** The frontend's component tests run against the handlers in
  `frontend/src/mocks/handlers/`, which copy the backend's responses, error bodies and
  validation rules. When a pull request changes one of those, it updates the matching handler
  too. Otherwise the frontend's tests keep passing against the old behaviour.

`frontend/CLAUDE.md` explains how to run them (`npm run test:integration` against a running
backend). If the frontend side doesn't fit in this pull request, list it under **Tickets to
open** rather than leaving it unsaid.

### Style

- **Unit tests only** for now: no real DB, no Flask test client. Services get the `mock_session`
  fixture; routes and decorators run inside `app.test_request_context(...)` and are called
  directly (see `tests/conftest.py`). The one exception is `tests/e2e/` (marker `e2e`), whose
  journeys drive the routes through Flask's test client on the in-memory database (ADR-0031).
- **Layout:** `tests/<module>/test_<feature>_<aspect>.py`, e.g.
  `tests/events/test_submit_event_request_validation.py`. Module-specific fixtures go in
  `tests/<module>/conftest.py`.
- **Traceability:** every test module sets `pytestmark = pytest.mark.<marker>`, where the marker
  is the story (`scrum_19`) declared in `pytest.ini`. The module docstring names the story and
  which ACs/ADRs it covers.
- **Test names** state the behaviour as a sentence:
  `test_unknown_email_and_wrong_password_produce_identical_errors`, not `test_login_2`.
- One behaviour per test. Arrange / act / assert separated by blank lines.
- Tables of cases use `@pytest.mark.parametrize` with `("name", "other")` tuples.
- Assert on side effects that matter: `mock_session.commit.assert_called_once()`,
  `rollback.assert_not_called()`.
- Determinism: pass a fixed `today` (the `today` fixture), inject factories instead of relying
  on randomness, never sleep.
- Replace collaborators with `monkeypatch.setattr(module, "name", fake)` or the injected
  keyword arguments; don't patch internals you don't own.
- Fixture factories (`make_user`, `token_for`) build in-memory objects; add new ones to the
  nearest `conftest.py` instead of repeating setup in every test.

## 15. Commits

Commits are **layered**: each one is a single, self-contained step, stacked on the ones before
it. A reviewer can read them one at a time, and any one can be reverted or bisected cleanly.

- **One logical change per commit.** A rename, a refactor, a feature and a docs update are
  separate commits, even when they were made together and even when they touch the same file
  (split the file's changes between commits).
- **Every commit stands on its own.** Check out any commit, and `ruff check .`,
  `ruff format --check .` and `pytest` pass. No "WIP" or "fix previous commit" commits in a PR;
  fold those into the commit they fix before asking for review.
- **Stacked in dependency order.** A commit relies only on commits below it: the shared helper
  before the code that calls it, the config before the docs that describe it.
- **Tests travel with their code.** Tests are written first (§14), but a behaviour change and
  its tests land in the same commit, so no commit is left red.
- **Usual order** when one PR has several: tooling and config → renames and moves →
  refactors → features → docs.
- **Message:** a Conventional Commit subject with the story, as in `CLAUDE.md` ("Git and
  PRs"). The body says *why*, and anything a reviewer should look at closely.
- **Merge with *Rebase and merge*,** never *Squash and merge*. Squashing collapses the
  layers into one commit on `main`, so they can no longer be reviewed, reverted or bisected
  one at a time. (A *merge commit* also keeps them, but adds noise.)
- **Answering review:** fold each fix into the commit it belongs to and force-push with
  `--force-with-lease`, rather than adding "address review" commits on top.

### Pull request description

GitHub fills a new PR with `.github/pull_request_template.md`. Keep its sections. Two of them
matter most, because nobody can find this information in the code afterwards:

- **Decisions made.** List every call the ACs didn't settle, each linked to its ADR. Split them
  into ones already *agreed with the team or customer* and *defaults to review*, so the
  reviewer knows which are still open. An ADR records why; the PR is where the team sees the
  decision and can object before it merges.
- **Tickets to open.** List follow-up work the PR found but doesn't do: tech debt, questions
  for the customer, gaps another story must cover. Say which story each belongs to, or that it
  needs a new ticket. A `# TODO` in the code is fine as well, but it doesn't replace the line
  here, because nobody plans work from TODOs. Whoever merges opens the tickets in Jira.

Write "None" rather than deleting either section, so a reviewer can tell "nothing to
report" from "forgot".
