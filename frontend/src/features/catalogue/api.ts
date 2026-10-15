import type { EventRequestStatus } from '@/config/eventStatus'
import { apiRequest } from '@/lib/api'

import type { CatalogueParams } from './searchParams'

/**
 * The catalogue API, as docs/adr/0032-event-catalogue-contract.md describes it, and an
 * Attendee's own events (docs/adr/0044-attendee-events-list.md).
 */
const CATALOGUE_PATHS = {
  EVENTS: '/api/events/catalogue',
  MY_EVENTS: '/api/events/registrations',
} as const

export interface CatalogueEvent {
  id: number
  reference: string
  name: string
  description: string
  /** ISO date-time with an offset, in business time. */
  starts_at: string
  ends_at: string
  venue: { id: number; name: string } | null
  capacity: number
  places_left: number
  is_full: boolean
  /** Whether the signed-in user holds a place. Always false for a visitor. */
  is_registered: boolean
}

export interface CataloguePage {
  items: CatalogueEvent[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

/** A place held at an event, as the backend returns it on registering. */
export interface Registration {
  id: number
  event_id: number
  status: 'registered'
  registered_at: string
}

/** An event the signed-in Attendee registered for, with the event's own status (ADR-0044). */
export interface MyEvent {
  event_id: number
  name: string
  /** ISO date-time with an offset, in business time. */
  starts_at: string
  ends_at: string
  event_status: EventRequestStatus
  /** The registration's own status. */
  status: 'registered'
  registered_at: string
}

/** One half of the Attendee's events. `message` is there only when the list is empty. */
export interface MyEventList {
  registrations: MyEvent[]
  message?: string
}

export const catalogueKeys = {
  all: ['catalogue'] as const,
  /**
   * One page for one viewer: `is_registered` depends on who asks, so a different user (or
   * signing in) reads the page again instead of seeing someone else's.
   */
  list: (params: CatalogueParams, viewerId: number | null) =>
    [...catalogueKeys.all, 'list', viewerId, params] as const,
  /**
   * One half of the signed-in Attendee's own events. Under `all`, so registering reads it
   * again; and keyed by viewer, so signing in as someone else never shows the last list.
   */
  mine: (when: string, viewerId: number | null) =>
    [...catalogueKeys.all, 'mine', viewerId, when] as const,
}

export function fetchCatalogue(params: CatalogueParams): Promise<CataloguePage> {
  return apiRequest<CataloguePage>(CATALOGUE_PATHS.EVENTS, { query: params })
}

/**
 * The signed-in Attendee's upcoming or past events, in the order the backend sends them.
 * `when` is sent as the page URL has it; the backend refuses one it doesn't know.
 */
export function fetchMyEvents(when: string): Promise<MyEventList> {
  return apiRequest<MyEventList>(CATALOGUE_PATHS.MY_EVENTS, { query: { when } })
}

/** Register the signed-in Attendee for an event. No body: the account is the registration. */
export function registerForEvent(eventId: number): Promise<Registration> {
  return apiRequest<Registration>(`${CATALOGUE_PATHS.EVENTS}/${eventId}/registrations`, {
    method: 'POST',
  })
}
