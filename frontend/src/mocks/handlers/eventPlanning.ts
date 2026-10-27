import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import type { EventHistoryEntry, RegistrationChanges } from '@/features/eventRequests/api'
import type { EventHistoryKind } from '@/features/eventRequests/eventHistory'
import type { FieldErrors } from '@/lib/api'

import { errorResponse, validationError } from '../responses'

import { releaseEventArrangements } from './booking'
import { MOCK_NOW } from './catalogueFixtures'
import { rejectEventEquipment } from './equipmentReservations'
import { NOTHING_PLANNED } from './eventPlanningFixtures'
import type { MockArrangement, MockArrangementStatus, MockPlanning } from './eventPlanningFixtures'
import { loadRegistrationChanges } from './eventPlanningRules'
import { addToHistory } from './eventRecordSections'
import { flaggedGaps } from './reassessmentRules'
import type { MockEventRequest } from './eventRequestFixtures'
import { assignedOrRefusal, objectBodyOrRefusal } from './eventRequests'
import { loadRejectionReason } from './eventReviewRules'

/**
 * The coordinator's planning actions on the stored event requests eventRequests.ts keeps, so
 * the record read afterwards shows the change: sending an event to safety review (SCRUM-97,
 * ADR-0047), marking it completed once it has ended, at the mock's "now", MOCK_NOW (SCRUM-68,
 * ADR-0027), its registration settings and withdrawal cut-off (SCRUM-69, ADR-0043, ADR-0086),
 * confirming it once every approval is in (SCRUM-49, ADR-0051) and rejecting it during planning
 * (SCRUM-49 AC9, AC10, ADR-0093), a rejection SCRUM-31's decision can't then change (AC12,
 * ADR-0106). Only the event's assigned coordinator may; the checks, their
 * order, the codes, messages and the gaps named are the backend's (ADR-0075). Each action that
 * changes something is written to the event's history as the backend writes it (SCRUM-33 AC4).
 * No notification is raised.
 */

const REQUEST_PATH = '/api/events/requests/:reference'
const NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE = 'Only an approved event can go to Safety Review.'
const SAFETY_REVIEW_NOT_READY_MESSAGE =
  'The event can go to Safety Review once every venue arrangement is approved and every ' +
  'equipment request has an outcome from Technical Support.'
const NO_VENUE_GAP = 'The event has no venue arranged.'
const NOT_CONFIRMED_MESSAGE = 'Only a confirmed event can be marked completed.'
const NOT_YET_ENDED_MESSAGE = 'The event has not ended yet.'
/** Singapore's offset: an event's dates and times are business time with none (ADR-0009). */
const BUSINESS_TIME_OFFSET = '+08:00'
const CAPACITY_REQUIRED_MESSAGE = 'A capacity is required to enable registration.'
const REGISTRATION_NOT_CONFIRMED_MESSAGE = 'Registration can be enabled only for a confirmed event.'
const CUT_OFF_NOT_BEFORE_START_MESSAGE = 'The withdrawal cut-off must be before the event starts.'
const NOT_IN_SAFETY_REVIEW_MESSAGE = 'Only an event in Safety Review can be confirmed.'
const CONFIRMATION_NOT_READY_MESSAGE =
  'The event can be confirmed once the Safety Officer has approved it, every venue ' +
  'arrangement is approved and every equipment request has an outcome from Technical ' +
  'Support.'
const SAFETY_NOT_APPROVED_GAP = 'The Safety Officer has not approved the event.'
const NOT_IN_PLANNING_FOR_REJECTION_MESSAGE =
  'Only an approved event or one in Safety Review can be rejected during planning.'
/** Where an event may be rejected during planning (`PLANNING_STATUSES`). */
const PLANNING_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
]
/** Arrangements no longer counted among the event's venues (`RETIRED_REQUEST_STATUSES`). */
const RETIRED_STATUSES: readonly MockArrangementStatus[] = ['withdrawn', 'released']
/** Arrangements holding their venue, which a rejection releases rather than withdraws. */
const HOLDING_STATUSES: readonly MockArrangementStatus[] = ['approved']

/** The settings the registration route changes, in the order the backend records them. */
const REGISTRATION_FIELDS = [
  'registration_enabled',
  'registration_capacity',
  'withdrawal_cut_off',
] as const

/** One history entry by the coordinator at the mock's "now", as `record_event_history` writes it. */
function entryBy(
  coordinatorName: string,
  kind: EventHistoryKind,
  details: Record<string, unknown>,
): EventHistoryEntry {
  return { kind, occurred_at: MOCK_NOW, actor_name: coordinatorName, details }
}

/** A 409 with the reasons behind it, as the backend's gates send it (ADR-0047, ADR-0051). */
function refusalWithGaps(code: string, message: string, details: FieldErrors) {
  return HttpResponse.json({ error: code, message, details }, { status: 409 })
}

/** What the gates count for the event; an event the mock plans nothing for has nothing. */
function planningOf(stored: MockEventRequest): MockPlanning {
  return stored.planning ?? NOTHING_PLANNED
}

/**
 * Why the event's venues hold it back, as `_venue_gaps` words it: no venue at all, or each
 * active arrangement (a withdrawn or released one is retired) that isn't approved, with its status, then each
 * reason a significant change flagged one (SCRUM-33 AC6, SCRUM-58 AC3).
 */
function venueGaps(planning: MockPlanning): string[] {
  const active = planning.arrangements.filter(
    (arrangement) => !RETIRED_STATUSES.includes(arrangement.status),
  )
  if (active.length === 0) {
    return [NO_VENUE_GAP]
  }
  const gaps: string[] = []
  for (const arrangement of active) {
    if (arrangement.status !== 'approved') {
      gaps.push(`Venue arrangement ${arrangement.id} is ${arrangement.status}.`)
    }
  }
  for (const arrangement of active) {
    gaps.push(...flaggedGaps(arrangement.id, arrangement.reassessmentFlags))
  }
  return gaps
}

/** Each equipment request still waiting on Technical Support, as `_equipment_gaps` words it. */
function equipmentGaps(planning: MockPlanning): string[] {
  return planning.equipmentWithoutOutcome.map(
    (lineId) => `Equipment request ${lineId} has no outcome from Technical Support.`,
  )
}

/** The venue and equipment gaps by area, an area with none left out (`_arrangement_gaps`). */
function arrangementGaps(planning: MockPlanning): FieldErrors {
  const heldBack: FieldErrors = {}
  const venues = venueGaps(planning)
  if (venues.length > 0) {
    heldBack.venue_arrangements = venues
  }
  const equipment = equipmentGaps(planning)
  if (equipment.length > 0) {
    heldBack.equipment = equipment
  }
  return heldBack
}

/** Whether the event's end (`end_date` + `end_time`, business time) is now or past (ADR-0027). */
function hasEnded(stored: MockEventRequest): boolean {
  const { end_date: endDate, end_time: endTime } = stored.request
  const endsAt = Date.parse(`${endDate ?? ''}T${endTime ?? ''}${BUSINESS_TIME_OFFSET}`)
  return Date.parse(MOCK_NOW) >= endsAt
}

/** Whether the event's start (`proposed_date` + `start_time`, business time) is at or before `instant`. */
function startsBy(stored: MockEventRequest, instant: string): boolean {
  const { proposed_date: startDate, start_time: startTime } = stored.request
  const startsAt = Date.parse(`${startDate ?? ''}T${startTime ?? ''}${BUSINESS_TIME_OFFSET}`)
  return startsAt <= Date.parse(instant)
}

/** An event's registration settings as the backend stores them. */
type RegistrationState = Pick<
  MockPlanning,
  'registration_enabled' | 'registration_capacity' | 'withdrawal_cut_off'
>

/**
 * The settings once `changes` apply, as `_settings_after` works them out: what isn't sent stays,
 * except whether registration is open on an event that never had a capacity, which follows the
 * organiser's answer (SCRUM-69 AC1, ADR-0043). A cut-off sent as null is cleared (ADR-0086).
 */
function settingsAfter(stored: MockEventRequest, changes: RegistrationChanges): RegistrationState {
  const planning = planningOf(stored)
  let enabled = planning.registration_enabled
  if (changes.registration_enabled !== undefined) {
    enabled = changes.registration_enabled
  } else if (planning.registration_capacity === null) {
    enabled = stored.request.registration_required
  }
  return {
    registration_enabled: enabled,
    registration_capacity: changes.registration_capacity ?? planning.registration_capacity,
    withdrawal_cut_off:
      changes.withdrawal_cut_off === undefined
        ? planning.withdrawal_cut_off
        : changes.withdrawal_cut_off,
  }
}

/**
 * Why the settings are refused, in the backend's order: open with no capacity, open before the
 * event is confirmed, then, open or closed, a capacity below the number registered (ADR-0043),
 * then a cut-off sent for the event's start or later; one already saved isn't checked (ADR-0086).
 */
function registrationRefusal(
  stored: MockEventRequest,
  settings: RegistrationState,
  changes: RegistrationChanges,
) {
  if (settings.registration_enabled && settings.registration_capacity === null) {
    return validationError({ registration_capacity: [CAPACITY_REQUIRED_MESSAGE] })
  }
  if (settings.registration_enabled && stored.request.status !== EVENT_REQUEST_STATUS.CONFIRMED) {
    return errorResponse(409, 'registration_not_enablable', REGISTRATION_NOT_CONFIRMED_MESSAGE)
  }
  const { registeredCount } = planningOf(stored)
  if (settings.registration_capacity !== null && settings.registration_capacity < registeredCount) {
    const message = `Capacity cannot be lower than the ${registeredCount} places already taken.`
    return validationError({ registration_capacity: [message] })
  }
  const cutOff = changes.withdrawal_cut_off
  if (typeof cutOff === 'string' && startsBy(stored, cutOff)) {
    return validationError({ withdrawal_cut_off: [CUT_OFF_NOT_BEFORE_START_MESSAGE] })
  }
  return null
}

/**
 * One `field_changed` entry per setting that differs from what is saved, as
 * `_record_field_changes` writes them: no setting is a significant change.
 */
function settingChanges(
  stored: MockEventRequest,
  settings: RegistrationState,
  coordinatorName: string,
): EventHistoryEntry[] {
  const saved = planningOf(stored)
  const entries: EventHistoryEntry[] = []
  for (const field of REGISTRATION_FIELDS) {
    if (saved[field] === settings[field]) {
      continue
    }
    const details = {
      field,
      previous_value: saved[field],
      new_value: settings[field],
      significant: false,
    }
    entries.push(entryBy(coordinatorName, 'field_changed', details))
  }
  return entries
}

/** What a rejection leaves of the event's arrangements, and the history it writes for them. */
interface Release {
  arrangements: MockArrangement[]
  withdrawals: EventHistoryEntry[]
}

/**
 * The event's arrangements once it is rejected, as `release_event_arrangements` leaves them:
 * one holding its venue is released, any other still active is withdrawn with its own history
 * entry, and a retired one stays as it is.
 */
function releaseArrangements(planning: MockPlanning, coordinatorName: string): Release {
  const release: Release = { arrangements: [], withdrawals: [] }
  for (const arrangement of planning.arrangements) {
    if (RETIRED_STATUSES.includes(arrangement.status)) {
      release.arrangements.push(arrangement)
    } else if (HOLDING_STATUSES.includes(arrangement.status)) {
      release.arrangements.push({ ...arrangement, status: 'released' })
    } else {
      release.arrangements.push({ ...arrangement, status: 'withdrawn' })
      const details = { venue_booking_request_id: arrangement.id, venue_id: arrangement.venueId }
      release.withdrawals.push(entryBy(coordinatorName, 'venue_arrangement_withdrawn', details))
    }
  }
  return release
}

export const eventPlanningHandlers: RequestHandler[] = [
  http.post(`${REQUEST_PATH}/safety-review`, ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { coordinator, stored } = found
    if (stored.request.status !== EVENT_REQUEST_STATUS.APPROVED) {
      return errorResponse(409, 'safety_review_not_allowed', NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE)
    }
    const heldBack = arrangementGaps(planningOf(stored))
    if (Object.keys(heldBack).length > 0) {
      return refusalWithGaps('safety_review_not_allowed', SAFETY_REVIEW_NOT_READY_MESSAGE, heldBack)
    }

    stored.request.status = EVENT_REQUEST_STATUS.SAFETY_REVIEW
    addToHistory(stored.request.reference, [
      entryBy(coordinator.full_name, 'safety_review_requested', {}),
    ])
    return HttpResponse.json(stored.request)
  }),

  http.post(`${REQUEST_PATH}/complete`, ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { coordinator, stored } = found
    if (stored.request.status !== EVENT_REQUEST_STATUS.CONFIRMED) {
      return errorResponse(409, 'request_not_completable', NOT_CONFIRMED_MESSAGE)
    }
    if (!hasEnded(stored)) {
      return errorResponse(409, 'request_not_completable', NOT_YET_ENDED_MESSAGE)
    }

    stored.request.status = EVENT_REQUEST_STATUS.COMPLETED
    addToHistory(stored.request.reference, [entryBy(coordinator.full_name, 'event_completed', {})])
    return HttpResponse.json(stored.request)
  }),

  http.post(`${REQUEST_PATH}/confirm`, ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { coordinator, stored } = found
    if (stored.request.status !== EVENT_REQUEST_STATUS.SAFETY_REVIEW) {
      return errorResponse(409, 'confirmation_not_allowed', NOT_IN_SAFETY_REVIEW_MESSAGE)
    }
    const planning = planningOf(stored)
    const heldBack: FieldErrors = {}
    if (!planning.isSafetyApproved) {
      heldBack.safety_check = [SAFETY_NOT_APPROVED_GAP]
    }
    Object.assign(heldBack, arrangementGaps(planning))
    if (Object.keys(heldBack).length > 0) {
      return refusalWithGaps('confirmation_not_allowed', CONFIRMATION_NOT_READY_MESSAGE, heldBack)
    }

    stored.request.status = EVENT_REQUEST_STATUS.CONFIRMED
    addToHistory(stored.request.reference, [entryBy(coordinator.full_name, 'event_confirmed', {})])
    return HttpResponse.json(stored.request)
  }),

  http.patch(`${REQUEST_PATH}/registration`, async ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { coordinator, stored } = found
    const payload = await objectBodyOrRefusal(request)
    if ('refusal' in payload) {
      return payload.refusal
    }
    const loaded = loadRegistrationChanges(payload.body)
    if ('errors' in loaded) {
      return validationError(loaded.errors)
    }
    const settings = settingsAfter(stored, loaded.changes)
    const refused = registrationRefusal(stored, settings, loaded.changes)
    if (refused !== null) {
      return refused
    }

    addToHistory(stored.request.reference, settingChanges(stored, settings, coordinator.full_name))
    stored.planning = { ...planningOf(stored), ...settings }
    return HttpResponse.json({
      reference: stored.request.reference,
      registration_required: stored.request.registration_required,
      ...settings,
    })
  }),

  http.post(`${REQUEST_PATH}/reject`, async ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { coordinator, stored } = found
    if (!PLANNING_STATUSES.includes(stored.request.status)) {
      return errorResponse(409, 'rejection_not_allowed', NOT_IN_PLANNING_FOR_REJECTION_MESSAGE)
    }
    const payload = await objectBodyOrRefusal(request)
    if ('refusal' in payload) {
      return payload.refusal
    }
    const loaded = loadRejectionReason(payload.body)
    if ('errors' in loaded) {
      return validationError(loaded.errors)
    }

    const planning = planningOf(stored)
    const { arrangements, withdrawals } = releaseArrangements(planning, coordinator.full_name)
    const decision = { outcome: 'rejected' as const, reason: loaded.text }
    stored.request.status = EVENT_REQUEST_STATUS.REJECTED
    stored.record = {
      ...stored.record,
      decision: { ...decision, decided_by: coordinator.full_name, decided_at: MOCK_NOW },
    }
    addToHistory(stored.request.reference, [
      entryBy(coordinator.full_name, 'decision_recorded', { ...decision, during_planning: true }),
      ...withdrawals,
    ])
    stored.planning = { ...planning, arrangements }
    stored.rejectedDuringPlanning = true
    // The venues and equipment the backend frees live in the venue and equipment mocks' stores.
    releaseEventArrangements(stored.request.reference)
    rejectEventEquipment(stored.request.reference)
    return HttpResponse.json(stored.request)
  }),
]
