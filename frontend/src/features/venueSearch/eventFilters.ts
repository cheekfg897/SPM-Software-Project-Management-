import type { EventRequest } from '@/features/eventRequests/api'
import { toTimeInputValue } from '@/lib/businessTime'

import type { SearchFilters } from './searchParams'

/** A recorded value as a filter holds it: empty when the event has none. */
function orEmpty(value: string | null): string {
  return value ?? ''
}

/** A recorded time of day as a filter holds it, to the minute: empty when there is none. */
function timeOrEmpty(time: string | null): string {
  return time === null ? '' : toTimeInputValue(time)
}

/** The end date, only for an event that ends on a later day than it starts (ADR-0073). */
function laterEndDate(event: EventRequest): string {
  if (event.end_date === null || event.end_date === event.proposed_date) {
    return ''
  }
  return event.end_date
}

/**
 * The search's filters filled in from what an event recorded (SCRUM-90, ADR-0124): the period
 * from its date, times and end date, and the minimum capacity from its expected attendance.
 * Room layout, facilities and accessibility stay empty, because the event records those as free
 * text, and so does anything the event has not recorded. Location is not an event detail.
 */
export function filtersFromEvent(event: EventRequest): SearchFilters {
  return {
    date: orEmpty(event.proposed_date),
    start: timeOrEmpty(event.start_time),
    end: timeOrEmpty(event.end_time),
    end_date: laterEndDate(event),
    min_capacity: event.expected_attendance === null ? '' : String(event.expected_attendance),
    location: '',
    required_layout: '',
    required_facilities: [],
    required_accessibility: [],
  }
}
