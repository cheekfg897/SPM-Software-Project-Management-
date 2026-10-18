import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { FieldErrors } from '@/lib/api'

import { errorResponse } from '../responses'

import { NOTHING_PLANNED } from './eventPlanningFixtures'
import type { MockPlanning } from './eventPlanningFixtures'
import type { MockEventRequest } from './eventRequestFixtures'
import { assignedOrRefusal } from './eventRequests'

/**
 * The coordinator's planning actions on the stored event requests eventRequests.ts keeps, so
 * the record read afterwards shows the change: sending an event to safety review (SCRUM-97,
 * ADR-0047). Only the event's assigned coordinator may; the checks, their order, the codes,
 * messages and the gaps named are the backend's (ADR-0075).
 */

const REQUEST_PATH = '/api/events/requests/:reference'
const NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE = 'Only an approved event can go to Safety Review.'
const SAFETY_REVIEW_NOT_READY_MESSAGE =
  'The event can go to Safety Review once every venue arrangement is approved and every ' +
  'equipment request has an outcome from Technical Support.'
const NO_VENUE_GAP = 'The event has no venue arranged.'

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
]
