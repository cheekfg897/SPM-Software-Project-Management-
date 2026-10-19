import { ROUTES } from '@/config/routes'
import { formText } from '@/features/auth/formText'
import { toBusinessTimeIso } from '@/lib/businessTime'
import { positiveIdParam } from '@/lib/positiveIdParam'

import type { SuitabilityRequest, VenueSearchRequest } from './api'

/**
 * The search's filters live in the page URL (ADR-0073), as the form's own values: a date, two
 * times and an optional end date rather than the instants the backend takes. So does the venue
 * being checked against them. These helpers read them, write them, and build the backend's
 * requests from them; none of them filter anything.
 */

/** The URL parameter holding the id of the venue being checked (SCRUM-36). */
const VENUE_TO_CHECK = 'venue'

/**
 * The URL parameters naming the event, its flagged arrangement and that arrangement's venue, which
 * a search is finding a replacement for (SCRUM-92).
 */
const REPLACING_EVENT = 'event'
const REPLACED_ARRANGEMENT = 'replaces'
const REPLACED_VENUE = 'instead_of'

/** The filters with one value each, named as the form fields and URL parameters are. */
const SINGLE_FILTERS = [
  'date',
  'start',
  'end',
  'end_date',
  'min_capacity',
  'location',
  'required_layout',
] as const

/** The filters with a list of items: one URL parameter per item, one form line per item. */
const LIST_FILTERS = ['required_facilities', 'required_accessibility'] as const

type SingleFilter = (typeof SINGLE_FILTERS)[number]
type ListFilter = (typeof LIST_FILTERS)[number]

/** What the coordinator asked for, as typed. An empty string is a filter left empty. */
export type SearchFilters = Record<SingleFilter, string> & Record<ListFilter, string[]>

const ALL_FILTERS: readonly string[] = [...SINGLE_FILTERS, ...LIST_FILTERS]

/** The filters in the URL, or null when it holds none and nothing has been searched for. */
export function readFilters(params: URLSearchParams): SearchFilters | null {
  const hasAny = ALL_FILTERS.some((name) => params.has(name))
  if (!hasAny) {
    return null
  }
  return {
    date: params.get('date') ?? '',
    start: params.get('start') ?? '',
    end: params.get('end') ?? '',
    end_date: params.get('end_date') ?? '',
    min_capacity: params.get('min_capacity') ?? '',
    location: params.get('location') ?? '',
    required_layout: params.get('required_layout') ?? '',
    required_facilities: params.getAll('required_facilities'),
    required_accessibility: params.getAll('required_accessibility'),
  }
}

/** A box's lines as items: each trimmed, empty ones dropped. */
function itemsIn(text: string): string[] {
  const items: string[] = []
  for (const line of text.split('\n')) {
    const item = line.trim()
    if (item !== '') {
      items.push(item)
    }
  }
  return items
}

/** The filters as the coordinator submitted the form. */
export function filtersFrom(form: FormData): SearchFilters {
  return {
    date: formText(form, 'date'),
    start: formText(form, 'start'),
    end: formText(form, 'end'),
    end_date: formText(form, 'end_date'),
    min_capacity: formText(form, 'min_capacity'),
    location: formText(form, 'location'),
    required_layout: formText(form, 'required_layout'),
    required_facilities: itemsIn(formText(form, 'required_facilities')),
    required_accessibility: itemsIn(formText(form, 'required_accessibility')),
  }
}

/** The URL with these filters in place of the old ones. Empty filters are left out. */
export function withFilters(current: URLSearchParams, filters: SearchFilters): URLSearchParams {
  const next = new URLSearchParams(current)
  for (const name of ALL_FILTERS) {
    next.delete(name)
  }
  for (const name of SINGLE_FILTERS) {
    if (filters[name] !== '') {
      next.set(name, filters[name])
    }
  }
  for (const name of LIST_FILTERS) {
    for (const item of filters[name]) {
      next.append(name, item)
    }
  }
  return next
}

function orNull(value: string): string | null {
  return value === '' ? null : value
}

/**
 * The backend's request. The period is sent in business time and ends on the start date unless
 * an end date was given. Whether it is valid is the backend's call: its messages name the field.
 */
export function toSearchRequest(filters: SearchFilters): VenueSearchRequest {
  const endDate = filters.end_date === '' ? filters.date : filters.end_date
  return {
    start_time: toBusinessTimeIso(`${filters.date}T${filters.start}`),
    end_time: toBusinessTimeIso(`${endDate}T${filters.end}`),
    min_capacity: Number(filters.min_capacity),
    location: orNull(filters.location),
    required_layout: orNull(filters.required_layout),
    required_facilities: filters.required_facilities,
    required_accessibility: filters.required_accessibility,
  }
}

/** The check's request: the search's minimum capacity is the event's expected attendance. */
export function toSuitabilityRequest(filters: SearchFilters): SuitabilityRequest {
  return {
    expected_attendance: Number(filters.min_capacity),
    required_layout: orNull(filters.required_layout),
    required_facilities: filters.required_facilities,
    required_accessibility: filters.required_accessibility,
  }
}

/** The id of the venue being checked, or null when there is none (or it isn't an id). */
export function readVenueToCheck(params: URLSearchParams): number | null {
  return positiveIdParam(params, VENUE_TO_CHECK)
}

/** The URL checking `venueId`, the filters left as they are. */
export function withVenueToCheck(current: URLSearchParams, venueId: number): URLSearchParams {
  const next = new URLSearchParams(current)
  next.set(VENUE_TO_CHECK, String(venueId))
  return next
}

/** The flagged arrangement a search is finding a replacement venue for (SCRUM-92 AC6). */
export interface ReplacementSearch {
  /** The event's EVR- reference. */
  reference: string
  arrangementId: number
  /** The flagged arrangement's own venue: a replacement is always another venue (AC6). */
  venueId: number
}

/** The replacement the URL's search is for, or null when it is an ordinary search. */
export function readReplacementSearch(params: URLSearchParams): ReplacementSearch | null {
  const reference = params.get(REPLACING_EVENT)
  const arrangementId = positiveIdParam(params, REPLACED_ARRANGEMENT)
  const venueId = positiveIdParam(params, REPLACED_VENUE)
  if (reference === null || arrangementId === null || venueId === null) {
    return null
  }
  return { reference, arrangementId, venueId }
}

/** The search page set to `filters`, finding a venue to replace the flagged arrangement. */
export function replacementSearchPath(
  replacement: ReplacementSearch,
  filters: SearchFilters,
): string {
  const params = new URLSearchParams({
    [REPLACING_EVENT]: replacement.reference,
    [REPLACED_ARRANGEMENT]: String(replacement.arrangementId),
    [REPLACED_VENUE]: String(replacement.venueId),
  })
  return `${ROUTES.VENUE_SEARCH}?${withFilters(params, filters).toString()}`
}
