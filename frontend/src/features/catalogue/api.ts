import type { EventRequestStatus } from '@/config/eventStatus'
import { apiRequest } from '@/lib/api'

import type { CatalogueParams } from './searchParams'

/**
 * The catalogue API, as docs/adr/0032-event-catalogue-contract.md describes it, an Attendee's
 * own events (docs/adr/0044-attendee-events-list.md) and one of them (docs/adr/0109).
 */
const CATALOGUE_PATHS = {
  EVENTS: '/api/events/catalogue',
  MY_EVENTS: '/api/events/registrations',
  /** One event the signed-in Attendee registered for, by its EVR- reference. */
  myEvent: (reference: string) => `/api/events/registrations/${encodeURIComponent(reference)}`,
  /** POST registers the signed-in Attendee; DELETE withdraws them (SCRUM-53). */
  registrationsFor: (eventId: number) => `/api/events/catalogue/${eventId}/registrations`,
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

/** Whether the Attendee holds the place, or gave it up (SCRUM-53). */
export type RegistrationStatus = 'registered' | 'withdrawn'

/** A place at an event, as the backend returns it on registering or withdrawing. */
export interface Registration {
  id: number
  event_id: number
  status: RegistrationStatus
  registered_at: string
  /** When the Attendee withdrew (SCRUM-53); `null` while they hold the place. */
  withdrawn_at: string | null
}

/** An event the signed-in Attendee registered for, with the event's own status (ADR-0044). */
export interface MyEvent {
  event_id: number
  /** The event's EVR- reference: its page's address (SCRUM-24 AC11, docs/adr/0109). */
  reference: string
  name: string
  /** ISO date-time with an offset, in business time. */
  starts_at: string
  ends_at: string
  event_status: EventRequestStatus
  /** The registration's own status. */
  status: RegistrationStatus
  registered_at: string
  /** When the Attendee withdrew (SCRUM-53); `null` while they hold the place. */
  withdrawn_at: string | null
}

/** A venue an event is booked at, as the people going to it see it (SCRUM-24 AC11). */
export interface BookedVenue {
  name: string
  location: string
}

/**
 * One event the signed-in Attendee registered for, as its page shows it (SCRUM-24 AC11,
 * docs/adr/0109): what the catalogue shows of any event, its venues, the registration, and
 * whether the backend offers Withdraw.
 */
export interface MyRegisteredEvent {
  id: number
  reference: string
  name: string
  description: string
  /** ISO date-time with an offset, in business time. */
  starts_at: string
  ends_at: string
  event_status: EventRequestStatus
  venues: BookedVenue[]
  /** The registration's own status. */
  status: RegistrationStatus
  registered_at: string
  withdrawn_at: string | null
  /** The cut-off the coordinator recorded, or the start when there is none (SCRUM-53 AC3). */
  withdrawals_close_at: string
  /** Whether the Attendee may withdraw now: the backend decides (SCRUM-53). */
  can_withdraw: boolean
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
  /** One of the Attendee's events. Under `all`, so withdrawing reads it again. */
  myEvent: (reference: string, viewerId: number | null) =>
    [...catalogueKeys.all, 'my-event', viewerId, reference] as const,
  /** The withdrawals made, so a page can show a refusal after its button has gone. */
  withdrawals: () => [...catalogueKeys.all, 'withdrawals'] as const,
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

/** One event the signed-in Attendee registered for, held or withdrawn, whatever its status. */
export function fetchMyRegisteredEvent(reference: string): Promise<MyRegisteredEvent> {
  return apiRequest<MyRegisteredEvent>(CATALOGUE_PATHS.myEvent(reference))
}

/** Register the signed-in Attendee for an event. No body: the account is the registration. */
export function registerForEvent(eventId: number): Promise<Registration> {
  return apiRequest<Registration>(CATALOGUE_PATHS.registrationsFor(eventId), {
    method: 'POST',
  })
}

/**
 * Withdraw the signed-in Attendee from an event, giving the place back (SCRUM-53). The backend
 * refuses once withdrawals have closed, with when they closed in the error's details.
 */
export function withdrawFromEvent(eventId: number): Promise<Registration> {
  return apiRequest<Registration>(CATALOGUE_PATHS.registrationsFor(eventId), {
    method: 'DELETE',
  })
}
