# ADR-0030: The organiser who submitted a request is told whenever a coordinator is assigned to it

- **Status:** Accepted
- **Date:** 2026-09-26
- **Story:** SCRUM-39 Be notified about review and approval decisions
- **Extends:** [ADR-0015](0015-in-app-notifications.md) (in-app notifications), [ADR-0018](0018-least-loaded-coordinator-and-event-history.md) (who is told on submission), [ADR-0021](0021-coordinator-reassignment.md) (who is told on reassignment)

## Context
SCRUM-39 has six ACs. The Event Organiser is notified when an Event Coordinator is assigned to their request (AC1). They are notified when a clarification is requested, and the coordinator when it is answered (AC2), and when the request is approved or rejected, with the reason (AC3). The newly assigned coordinator is notified on assignment and on reassignment (AC4).

Week 7 customer change #5 (the Event Coordinator Lead) added two more, after this record was first written. The Lead is notified when a newly submitted request enters the unassigned queue (AC5), and the previously assigned coordinator when an event is reassigned away from them (AC6). The story's change note says assignment and reassignment are now the Lead's to perform.

AC4 is already met. The coordinator's `coordinator_assigned` notice is raised on a fresh submission (SCRUM-30, ADR-0018), on a submitted draft (SCRUM-20, ADR-0024) and on a reassignment (SCRUM-87, ADR-0021). ADR-0018 and ADR-0021 both left the organiser's side to this story.

AC2 and AC3 belong to other stories' work. Clarifications are SCRUM-32's: its own ACs need the clarification notices, so SCRUM-32 adds those kinds in its own migration ([ADR-0029](0029-clarification-requests.md)). Approval and rejection are SCRUM-31's decisions, and its AC10 raises their notices.

That leaves these questions open:
1. Who "the Event Organiser" is: the account that submitted the request, or everyone in its client organisation (ADR-0020).
2. Whether a reassignment counts as "a coordinator is assigned".
3. Whether the organiser's notice needs a new kind.
4. Where the notice is raised, given that three paths assign a coordinator.
5. What the organiser hears when no coordinator can be assigned.
6. How the migration is shaped, and where its test lives.
7. How AC4's evidence is recorded without duplicating tests.

## Decision
1. **The submitter only (39-1).** The organiser is `event_requests.organiser_id`, the account that submitted the request. Their colleagues can see the request (ADR-0020), but they didn't ask for it, and telling every colleague about every assignment would be noise. A regression-guard test pins this.
2. **Every assignment, reassignment included (39-2).** A reassignment means a new coordinator is assigned, and the organiser's contact changes (SCRUM-87 AC6). The organiser is told both times, as ADR-0021 deferred to this story.
3. **One new kind, `request_assigned` (39-3).** Its message is "An Event Coordinator has been assigned to your event request." `coordinator_assigned` says "You have been assigned to coordinate this event", which is the coordinator's notice and would be wrong for the organiser. A separate `coordinator_changed` kind for reassignments isn't needed: the organiser's record already shows who the coordinator is now.
4. **One shared helper (39-4).** `_notify_about_assignment(event_request, coordinator_id, session)` raises the coordinator's `coordinator_assigned`, then the organiser's `request_assigned`. Both submit paths (through `_notify_about_submission`) and `reassign_coordinator` call it, so the three paths can't drift apart. The two notices are separate writes after the change's own commit. If one fails, it is rolled back and logged with `kind=`, the other is still sent, and the reply still succeeds (ADR-0015).
5. **Unassigned: nobody is told (39-5).** A request saved with no Event Coordinator (ADR-0018) raises nothing, for the organiser too. AC1 is about an assignment, and none has happened. A "waiting for a coordinator" notice would be a new product decision, not what AC1 asks for.
6. **One migration, 0019, for `request_assigned` alone (39-6, R5-5).** It adds the value outside the transaction, and its downgrade deletes those rows and rebuilds `notification_kind` without the value, like 0015. Its revision id is `0019_add_review_kinds`, since `alembic_version.version_num` is `VARCHAR(32)`. The clarification kinds are SCRUM-32's, in its own migration ([ADR-0029](0029-clarification-requests.md)), so 0019 won't grow.
7. **The migration test lives in `tests/events/` (39-7)**, next to the fixtures every other migration test uses (`load_migration`, `render_migration_sql`, `assert_in_order`). Moving those fixtures to the root conftest would be a refactor with no second caller outside `tests/events/`.
8. **AC4's evidence is the existing tests, marked `scrum_39` (39-8).** They are the regression guards, not duplicates. On submission: `test_submit_event_request_notifies_coordinators.py` (the whole module). On a submitted draft: `test_a_submitted_draft_goes_to_the_least_loaded_coordinator_with_history_and_a_notification`. On reassignment: `test_reassign_coordinator_notifications.py` (the whole module). The no-coordinator case (39-5) is `test_with_no_event_coordinator_the_request_is_saved_unassigned_and_logged`.

## Consequences
- An organiser gets one `request_assigned` notice per assignment: one on submission and one per reassignment. It links to the event's page, where their record shows the new coordinator's contact (ADR-0018).
- A successful submission or reassignment now makes three commits, not two: the change itself, the coordinator's notice and the organiser's notice.
- The "nobody else is notified" tests for submission and reassignment no longer list the organiser.
- `pytest -m scrum_39` runs AC1's tests, AC4's guards and AC2's evidence.

## Met by other stories
- **AC2** (the organiser told a clarification is requested, the coordinator that it is answered): SCRUM-32 adds the notices, their kinds and its migration ([ADR-0029](0029-clarification-requests.md)); its `tests/events/test_clarification_notifications.py` carries the `scrum_39` marker as this story's evidence.
- **AC3** (approved or rejected, with the reason): SCRUM-31's AC10 raises these notices when the coordinator decides.

## Blocked
SCRUM-39's Week 7 ACs wait on the Event Coordinator Lead:
- **AC5** (the Lead told when a new request enters the unassigned queue): blocked by SCRUM-95. There is no Lead role to notify, and no unassigned queue for anyone to see ([ADR-0034](0034-coordinators-see-only-their-own-events.md)). Requests are still assigned automatically on submission (ADR-0018), so one is only unassigned when no Event Coordinator exists, which is logged as `event_request_unassigned`.
- **AC6** (the previous coordinator told when an event is reassigned away from them): blocked by SCRUM-95/96. Today only a request's own coordinator may reassign it (ADR-0021), so they would be told of their own action. The notice is useful once the Lead reassigns, and its kind and wording are best decided with that story.

## Revisit when
- The customer wants the organiser's colleagues told too, or the organiser told when a request is saved unassigned.
- SCRUM-95 lands: tell the Lead of each request that enters the unassigned queue (AC5).
- SCRUM-95/96 let the Lead reassign: tell the previous coordinator too (AC6), and drop the "previous coordinator isn't notified" note in `reassign_coordinator`.
