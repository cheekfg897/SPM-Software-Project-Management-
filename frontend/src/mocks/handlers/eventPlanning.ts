import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { RegistrationChanges } from '@/features/eventRequests/api'
import type { FieldErrors } from '@/lib/api'

import { errorResponse, validationError } from '../responses'

import { MOCK_NOW } from './catalogueFixtures'
import { NOTHING_PLANNED } from './eventPlanningFixtures'
import type { MockPlanning } from './eventPlanningFixtures'
import { loadRegistrationChanges } from './eventPlanningRules'
import type { MockEventRequest } from './eventRequestFixtures'
import { assignedOrRefusal, objectBodyOrRefusal } from './eventRequests'

/**
 * The coordinator's planning actions on the stored event requests eventRequests.ts keeps, so
 * the record read afterwards shows the change: sending an event to safety review (SCRUM-97,
 * ADR-0047), marking it completed once it has ended, at the mock's "now", MOCK_NOW (SCRUM-68,
 * ADR-0027), its registration settings (SCRUM-69, ADR-0043) and confirming it once every
 * approval is in (SCRUM-49, ADR-0051). Only the event's assigned coordinator may; the checks,
 * their order, the codes, messages and the gaps named are the backend's (ADR-0075). No
 * notification is raised.
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
const NOT_IN_SAFETY_REVIEW_MESSAGE = 'Only an event in Safety Review can be confirmed.'
const CONFIRMATION_NOT_READY_MESSAGE =
  'The event can be confirmed once the Safety Officer has approved it, every venue ' +
  'arrangement is approved and every equipment request has an outcome from Technical ' +
  'Support.'
const SAFETY_NOT_APPROVED_GAP = 'The Safety Officer has not approved the event.'

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
 * active arrangement (a withdrawn one is retired) that isn't approved, with its status.
 */
function venueGaps(planning: MockPlanning): string[] {
  const active = planning.arrangements.filter((arrangement) => arrangement.status !== 'withdrawn')
  if (active.length === 0) {
    return [NO_VENUE_GAP]
  }
  const gaps: string[] = []
  for (const arrangement of active) {
    if (arrangement.status !== 'approved') {
      gaps.push(`Venue arrangement ${arrangement.id} is ${arrangement.status}.`)
    }
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

/** An event's registration settings as the backend stores them. */
type RegistrationState = Pick<MockPlanning, 'registration_enabled' | 'registration_capacity'>

/**
 * The settings once `changes` apply, as `_settings_after` works them out: what isn't sent stays,
 * except whether registration is open on an event that never had a capacity, which follows the
 * organiser's answer (SCRUM-69 AC1, ADR-0043).
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
  }
}

/**
 * Why the settings are refused, in the backend's order: open with no capacity, open before the
 * event is confirmed, then, open or closed, a capacity below the number registered (ADR-0043).
 */
function registrationRefusal(stored: MockEventRequest, settings: RegistrationState) {
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
  return null
}

export const eventPlanningHandlers: RequestHandler[] = [
  http.post(`${REQUEST_PATH}/safety-review`, ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { stored } = found
    if (stored.request.status !== EVENT_REQUEST_STATUS.APPROVED) {
      return errorResponse(409, 'safety_review_not_allowed', NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE)
    }
    const heldBack = arrangementGaps(planningOf(stored))
    if (Object.keys(heldBack).length > 0) {
      return refusalWithGaps('safety_review_not_allowed', SAFETY_REVIEW_NOT_READY_MESSAGE, heldBack)
    }

    stored.request.status = EVENT_REQUEST_STATUS.SAFETY_REVIEW
    return HttpResponse.json(stored.request)
  }),

  http.post(`${REQUEST_PATH}/complete`, ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { stored } = found
    if (stored.request.status !== EVENT_REQUEST_STATUS.CONFIRMED) {
      return errorResponse(409, 'request_not_completable', NOT_CONFIRMED_MESSAGE)
    }
    if (!hasEnded(stored)) {
      return errorResponse(409, 'request_not_completable', NOT_YET_ENDED_MESSAGE)
    }

    stored.request.status = EVENT_REQUEST_STATUS.COMPLETED
    return HttpResponse.json(stored.request)
  }),

  http.post(`${REQUEST_PATH}/confirm`, ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { stored } = found
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
    return HttpResponse.json(stored.request)
  }),

  http.patch(`${REQUEST_PATH}/registration`, async ({ request, params }) => {
    const found = assignedOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }
    const { stored } = found
    const payload = await objectBodyOrRefusal(request)
    if ('refusal' in payload) {
      return payload.refusal
    }
    const loaded = loadRegistrationChanges(payload.body)
    if ('errors' in loaded) {
      return validationError(loaded.errors)
    }
    const settings = settingsAfter(stored, loaded.changes)
    const refused = registrationRefusal(stored, settings)
    if (refused !== null) {
      return refused
    }

    stored.planning = { ...planningOf(stored), ...settings }
    return HttpResponse.json({
      reference: stored.request.reference,
      registration_required: stored.request.registration_required,
      ...settings,
    })
  }),
]
