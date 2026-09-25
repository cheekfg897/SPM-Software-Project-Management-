# ADR-0013: Client organisations are recorded by internal users and organisers are linked at registration

- **Status:** Accepted
- **Date:** 2026-09-25
- **Story:** SCRUM-66 Record client organisations and link Organisers to them

## Context
SCRUM-7 and SCRUM-55 scope what an Event Organiser sees to "their own client organisation", but nothing created a client organisation or attached an organiser to one. The story leaves an open question for the customer: is Client Management expected in the first release, or should organisations be seeded reference data? The Jira story has no answer yet, and role-based access can't wait for one.

The `users` table already had a free-text `organisation` column from SCRUM-65. Free text can't back "exactly one organisation": two organisers typing "Acme" and "ACME Ltd" would be in different organisations.

## Decision
- **A `client_organisations` table** with `name` (unique), `contact_name`, `contact_email` and an optional `contact_phone`, owned by a new `organisations` module.
- **Internal users record and list them** through `POST /api/organisations` and `GET /api/organisations`, restricted to `INTERNAL_ROLES`. That is the whole of "Client Management" for now: no update, deactivate or delete, and no seeding.
- **Attendees and organisers cannot read organisation details** (AC5). Those two routes are the only place organisation details are exposed; `GET /api/auth/me` shows an organiser only their own `organisation_id`.
- **An Event Organiser is linked at registration:** `POST /api/auth/register` takes `organisation_id`, which is required when `role` is `event_organiser` and must be absent for every other role. It must name an existing organisation. The organiser gets the id from the internal user who recorded the organisation.
- **The free-text `users.organisation` column is dropped** and replaced by `users.organisation_id`, a nullable foreign key. Nullable because attendees and internal staff have no organisation, and because organiser accounts created before this change can't be linked automatically. "Exactly one organisation" is an application rule enforced at registration, not a database constraint.
- **An event request records the organiser's organisation** (`event_requests.organisation_id`, nullable, indexed) when it is submitted, copied from the organiser's account. An organiser whose account has no organisation is refused with `403 organiser_without_organisation` until an internal user links them.

## Consequences
- SCRUM-7 can filter `event_requests` by `organisation_id` with no cross-module join. Requests submitted before this change have `NULL` and so appear in no organisation's list, which is right: nobody can claim them.
- Organiser rows that pre-date migration `0007` have no organisation and can't submit until linked. Linking an existing account is not in this story.
- Registration is public and organisation ids are sequential, so anyone can register as an organiser of any organisation by guessing its id. This is the same trust gap as internal roles self-registering (the `TODO(product)` on the register route), and closes with it: once accounts are provisioned or approved by an internal user, so is the organisation link.
- Names are unique exactly as typed (case-sensitive); "Acme" and "acme" are two organisations.
- Every SCRUM-65 registration test that used the free-text field now registers an attendee; the organiser path is tested under SCRUM-66.

## Revisit when
- The customer answers the open question. If organisations are to be seeded, the two routes go and a seed migration replaces them; if fuller Client Management is wanted, update/deactivate and "link an existing organiser" stories are added.
- SCRUM-7 or SCRUM-55 needs organisers to see their organisation's name, not just its id.
- The customer decides how accounts are provisioned (the `TODO(product)` on the register route); organisers joining an organisation should go through the same approval.
- A story needs to move an organiser between organisations; then decide whether their past event requests move with them.
