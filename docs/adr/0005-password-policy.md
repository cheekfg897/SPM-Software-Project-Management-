# ADR-0005: Passwords need at least 8 characters, a letter and a digit

- **Status:** Accepted
- **Date:** 2026-09-25 (recorded from the Sprint 1 `STORIES.md`; the code has followed it since then)
- **Story:** SCRUM-65 Create an account (AC1: "supplying ... a password")

## Context
The AC requires a password but sets no strength rule. With no rule, a one-character password
would be accepted.

## Decision
- A password must be at least `PASSWORD_MIN_LENGTH` characters (default **8**, set in config so
  it can be tuned without a code change), and contain **at least one letter and one digit**.
- A rejected password gets a message naming the rule it failed, not a generic "too weak".
- Passwords are hashed with Werkzeug's scrypt before storage and are never returned or logged.

## Consequences
- Validation lives in `validate_password_strength` in `app/modules/auth/schemas.py`.
- No check against lists of breached or common passwords, so `Password1` is accepted.

## Revisit when
- The customer states security requirements for passwords.
- A breached-password check (e.g. against a known-compromised list) is wanted.
