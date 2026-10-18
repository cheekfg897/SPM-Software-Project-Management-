import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import type { VenueMatch } from '@/features/venueSearch/api'

import {
  errorResponse,
  notAllowed,
  notAuthenticated,
  readBody,
  validationError,
} from '../responses'

import { accountForRequest } from './auth'
import { MOCK_SEARCH_VENUES } from './venueSearchFixtures'
import type { MockSearchVenue } from './venueSearchFixtures'
import {
  instantOf,
  isFree,
  positiveNumberErrors,
  requirementErrors,
  requirementsFrom,
  searchErrors,
  unmetRequirements,
} from './venueSearchRules'
import type { MockRequirements, MockUnmetRequirement } from './venueSearchRules'

/**
 * The venue module's search (SCRUM-35), venue list and suitability check (SCRUM-36), answering
 * as backend/app/modules/venue/routes.py does, error bodies included.
 */

const VENUES_PATH = '/api/venues'
const SEARCH_PATH = `${VENUES_PATH}/search`
const SUITABILITY_PATH = `${VENUES_PATH}/:venueId/suitability`
const VENUE_NOT_FOUND_MESSAGE = 'Venue not found.'
/** The backend's NO_MATCHES_MESSAGE (venue/routes.py, SCRUM-35 AC4). */
const NO_MATCHES_MESSAGE = 'No venues match your search criteria.'

const venues: readonly MockSearchVenue[] = Object.values(MOCK_SEARCH_VENUES)

/** The response to refuse a caller whose role isn't in `allowed`, or null to go on. */
function refusalFor(request: Request, allowed: readonly Role[]) {
  const user = accountForRequest(request)
  if (user === undefined) {
    return notAuthenticated()
  }
  if (!allowed.includes(user.role)) {
    return notAllowed()
  }
  return null
}

/** A blank location means anywhere, as the backend trims it to nothing. */
function locationFilter(value: unknown): string | null {
  if (typeof value !== 'string' || value.trim() === '') {
    return null
  }
  return value.trim().toLowerCase()
}

/** It offers everything asked for, so what it meets is exactly what was requested. */
function toMatch(venue: MockSearchVenue, requirements: MockRequirements): VenueMatch {
  return {
    id: venue.id,
    name: venue.name,
    capacity: venue.capacity,
    location: venue.location,
    matched_requirements: {
      facilities: requirements.facilities,
      accessibility_features: requirements.accessibility,
      layout: requirements.layout,
    },
  }
}

function byName(left: { name: string }, right: { name: string }): number {
  return left.name.localeCompare(right.name)
}

function search(body: Record<string, unknown>): VenueMatch[] {
  const start = instantOf(body.start_time)
  const end = instantOf(body.end_time)
  const minCapacity = Number(body.min_capacity)
  const location = locationFilter(body.location)
  const requirements = requirementsFrom(body)

  const matches: VenueMatch[] = []
  for (const venue of venues) {
    const isCandidate =
      venue.is_active &&
      venue.capacity >= minCapacity &&
      (location === null || venue.location.toLowerCase().includes(location)) &&
      unmetRequirements(venue, requirements).length === 0 &&
      isFree(venue, start, end)
    if (isCandidate) {
      matches.push(toMatch(venue, requirements))
    }
  }
  return matches.sort(byName)
}

/** Capacity first, then what `unmetRequirements` finds, as check_venue_suitability lists them. */
function suitabilityReasons(
  venue: MockSearchVenue,
  body: Record<string, unknown>,
): MockUnmetRequirement[] {
  const reasons: MockUnmetRequirement[] = []
  const attendance = Number(body.expected_attendance)
  if (venue.capacity < attendance) {
    reasons.push({
      requirement: 'capacity',
      message: `Expected attendance of ${attendance} exceeds the venue's capacity of ${venue.capacity}.`,
    })
  }
  reasons.push(...unmetRequirements(venue, requirementsFrom(body)))
  return reasons
}

export const venueSearchHandlers: RequestHandler[] = [
  http.get(VENUES_PATH, ({ request }) => {
    const user = accountForRequest(request)
    if (user === undefined) {
      return notAuthenticated()
    }
    return HttpResponse.json(venues.filter((venue) => venue.is_active).sort(byName))
  }),

  http.post(SEARCH_PATH, async ({ request }) => {
    const refusal = refusalFor(request, [ROLE.EVENT_COORDINATOR])
    if (refusal !== null) {
      return refusal
    }
    const body = await readBody(request)
    const errors = searchErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }

    const results = search(body)
    if (results.length === 0) {
      return HttpResponse.json({ results, message: NO_MATCHES_MESSAGE })
    }
    return HttpResponse.json({ results })
  }),

  http.post(SUITABILITY_PATH, async ({ request, params }) => {
    const refusal = refusalFor(request, [ROLE.EVENT_COORDINATOR, ROLE.VENUE_STAFF])
    if (refusal !== null) {
      return refusal
    }
    const body = await readBody(request)
    const errors = {
      ...positiveNumberErrors(body, 'expected_attendance'),
      ...requirementErrors(body),
    }
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const venue = venues.find((candidate) => candidate.id === Number(params.venueId))
    if (venue === undefined) {
      return errorResponse(404, 'not_found', VENUE_NOT_FOUND_MESSAGE)
    }

    const reasons = suitabilityReasons(venue, body)
    return HttpResponse.json({ suitable: reasons.length === 0, reasons })
  }),
]
