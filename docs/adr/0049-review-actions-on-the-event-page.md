# ADR-0049: The coordinator reviews, decides and asks for clarification on the event page; the organiser answers there

- **Status:** Accepted; every decision below is a default to review with the team
- **Date:** 2026-10-17
- **Stories:** SCRUM-31 Review and decide a submitted request; SCRUM-32 Ask the Organiser for
  clarification
- **Extends:** [ADR-0028](0028-review-and-decide.md), [ADR-0029](0029-clarification-requests.md),
  [ADR-0046](0046-event-request-detail-page.md)

## Context
The backend has had the four routes since Sprint 2 (ADR-0028, ADR-0029):

- `POST /api/events/requests/<reference>/review`: the assigned coordinator moves a submitted
  request to under review.
- `POST …/decide` with `{"outcome", "reason"}`: the assigned coordinator approves or rejects.
- `POST …/request-clarification` with `{"message"}`: the assigned coordinator asks a question.
- `POST …/resubmit` with `{"response", …}`: an organiser of the request's organisation answers.

The web app shows an event's record (ADR-0046) but none of these actions, which ADR-0046 left
for this PR. As numbered in Jira on 2026-10-17, SCRUM-31 AC3 says the coordinator can move a
submitted request to Under Review, AC4 that approving moves it to Approved and rejecting needs a
reason, AC5 that nobody else may, and AC6 that a decided request can be decided again with a
reason. SCRUM-32 AC1 says the coordinator records a clarification request with a message, AC2
that the response returns the event to Under Review, AC3 that approval is refused while a
question is outstanding, and AC4 that both sides stay on the record.

**SCRUM-32 changed on 17 Oct**, after the story was Done: the customer now wants the
*coordinator* to record the organiser's response (the discussion happens offline), and the
organiser to have no edit or resubmit action. The backend on `main` still has the organiser's
`/resubmit` and no route for a coordinator to record a response.

Six things are left open.

## Decision
1. **Where.** The coordinator's actions sit in a "Review" section near the top of their copy of
   the event page (`/events/<reference>`), under the links to Venue requests and Equipment. The
   organiser's answer sits at the foot of the "Clarifications" section on their copy
   (`/organiser/requests/<reference>`), under the open question it answers.
2. **Which actions show in which status.** A button shows only where it can apply; whether the
   action is allowed is still the backend's call, and its refusal is shown as it comes. The one
   table, `REVIEW_ACTIONS_BY_STATUS`, is typed over every status:

   | Status | Start review | Approve | Reject | Ask for clarification |
   |---|---|---|---|---|
   | submitted | yes | yes | yes | |
   | under_review | | yes | yes | yes |
   | awaiting_clarification | | | yes | |
   | approved, rejected | | yes | yes | |
   | draft, confirmed, completed, cancelled | | | | |

   - A decision can be made straight from `submitted` (ADR-0028 decision 6), so both show there.
   - **Approve is hidden while a question is outstanding** (SCRUM-32 AC3): the backend would
     always refuse it. Reject stays, as the backend allows it (ADR-0029 decision 14).
   - **A decided request offers both outcomes again** (SCRUM-31 AC6). The page doesn't read the
     record's equipment lines (ADR-0046), so it can't know the decision is locked (AC7). It
     offers the change, and shows the backend's `decision_locked` message.
   - With nothing to offer, the section isn't drawn.
3. **Inline forms, not modals.** Each action is a small card with a heading, a text box where it
   needs one and its button, like the booking decision form. A modal would need focus trapping
   and its own tests, and gives nothing a single-column page lacks.
4. **One reason box for both outcomes.** It is sent only when something is typed, so a first
   approval may leave it empty. Whether a reason is needed (a rejection, or any change of
   decision) is the backend's rule: its field message shows under the box. The page doesn't
   check it first.
5. **The organiser answers with a response only, and the answer form follows the backend as it
   is today.** The backend's `/resubmit` is the only way an event leaves
   `awaiting_clarification`, so without it a request asked a question could never be approved
   in the web app. The form sends `{"response"}` and no amendments: since 17 Oct the customer
   doesn't want organisers amending a submitted request. When the backend lets the coordinator
   record the response, the form moves to the coordinator's page.
6. **After each action, every event-request query is read again** (`eventRequestKeys.all`): the
   record and both lists. The page shows the new status, decision and question because the
   backend says so, not because the cache was edited.

**The mock** (`src/mocks/handlers/eventRequests.ts`) answers the four routes as the backend
does: the same roles, scope (only the assigned coordinator; any organiser of the organisation),
check order, status changes, error codes and messages, field messages and trimming. A decision
or question appears on the record with the caller's name and the mock's "now". Two accounts
are added so the actions have data no other test reads: Priya Nair (id 10), a coordinator, and
Sara Lee (id 11), an organiser of organisation 2. One of Priya's approved events has an
equipment request, so its decision is locked.

## Consequences
- A coordinator can take a request from Submitted to a decision in the web app, and an
  organiser can answer a question, so SCRUM-41's journey can run in a browser.
- The mock raises no notifications for these actions; the notifications mock seeds its own.
- The mock's `/resubmit` takes only `response`. The backend also takes amendments (ADR-0029
  decision 9), which the web app doesn't send, so the mock calls them unknown fields.
- The mock locks a decision only for an equipment request, as the backend does today
  (`_has_arrangements`, `# TODO: SCRUM-42`).

## Revisit when
- **The backend follows SCRUM-32's 17 Oct change**: move the answer form to the coordinator's
  page and drop the organiser's.
- The record shows the event's equipment lines or venue booking requests: the page can then
  hide a change of decision that the lock would refuse.
- The customer wants a decision or question confirmed before it is sent.
