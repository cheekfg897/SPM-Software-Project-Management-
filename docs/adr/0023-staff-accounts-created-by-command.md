# ADR-0023: Staff accounts are created by a `flask create-staff-user` command, not self-registration

- **Status:** Accepted
- **Date:** 2026-09-26
- **Story:** SCRUM-88 Internal staff roles can self-register (SCRUM-65)

## Context
SCRUM-65's AC3 and AC4 already say self-registration is external-only: a new account is created as Event Organiser or Attendee and never as an internal role, and Event Coordinator, Venue Staff and Technical Support Staff accounts "cannot be self-created". The code didn't follow this: `RegisterSchema.role` accepted all five roles, so `POST /api/auth/register` could create any of the three staff roles too (found in PR #13 review, tracked as SCRUM-88). The route carried a `TODO(product)` recording the gap.

The code diverged from the ACs because of SCRUM-65's open question: "Are internal staff accounts provisioned by ConnectSphere, and if so by whom? None of the five roles is an administrator." With no admin role and no "approve this account" workflow anywhere in ConnectSphere, simply refusing internal roles at the route leaves no way to create one at all. This ADR is an interim answer to that question, not a final one: it lets the ACs be met now while leaving the real provisioning decision for the customer.

## Decision
- **`POST /api/auth/register` accepts only `EXTERNAL_ROLES`** (`event_organiser`, `attendee`). An internal role is a `400 validation_error` on the `role` field, the same as an unknown role. The `TODO(product)` is removed.
- **A new Flask CLI command, `flask create-staff-user`,** creates an `event_coordinator`, `venue_staff` or `technical_support_staff` account. It takes `--email`, `--full-name` and `--role`, and prompts for the password twice, hidden; there is deliberately no `--password` option, so a password never lands in shell history or a process listing.
- **A command instead of SCRUM-88's suggested "seed staff accounts".** A seed would fix staff emails and passwords in code or a migration, shared by every deployment and awkward to change. The command lets whoever runs it choose the email and password for their own deployment, and the payload goes through the same validation as a real registration.
- **Whoever operates the deployment runs it.** A shell on the machine or container running ConnectSphere is the trust boundary, the same as `flask db upgrade` already is. No admin role and no HTTP route are added; an HTTP endpoint would need its own caller-permission story.
- **The command reuses `register_user`'s machinery.** Both call a shared `_save_new_user` helper for the normalise-check-hash-persist-commit sequence, and `CreateStaffUserSchema` reuses `RegisterSchema`'s email, password and full-name rules through a common `_NewUserSchema`. Only the allowed roles, the entry point, and the absent `organisation_id` field differ.
- **No `organisation_id` for staff:** `CreateStaffUserSchema` has no such field, since staff never belong to a client organisation (ADR-0013).

## Consequences
- Self-registration is public only for `event_organiser` and `attendee`. The one place that self-registered a staff account, `README.md`'s curl example, now registers an attendee instead.
- ADR-0018's "coordinators register themselves" now means an Event Coordinator account is created by whoever runs `flask create-staff-user`, not typed into the public form.
- Provisioning staff needs shell access to the deployment; there is no in-app way to promote a user or invite a colleague.
- Staff accounts self-registered before this change are unaffected.
- **Known risk, out of scope:** an Event Organiser still registers with a plain, sequential `organisation_id` (ADR-0013, ADR-0020), so anyone can guess another organisation's id and register as one of its organisers. This is the same shape of trust gap as internal roles self-registering, and it is not fixed here; it needs its own story. Tracked as a follow-up ticket.

## Revisit when
- The customer answers SCRUM-65's open question directly, e.g. wants an in-app "invite a colleague" flow or a super-admin role.
- The organiser/organisation-id risk above gets its own story.
- ConnectSphere grows a deployment story (who has shell access, how secrets are managed) that this ADR's trust boundary should be checked against.
