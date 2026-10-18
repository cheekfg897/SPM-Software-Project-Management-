/**
 * Helpers that take an event through the real backend to the point a check needs: submitted by
 * a new organiser, assigned by a Lead and approved by the staff account (an Event Coordinator),
 * then given venues by Venue Staff. The Lead and Venue Staff accounts are optional: they come
 * from INTEGRATION_LEAD_* and INTEGRATION_VENUE_STAFF_*, and the checks that need them skip
 * without them. CI makes both (frontend.yml).
 */

import { register } from '@/features/auth/api'
import { assignCoordinator } from '@/features/lead/api'
import { createOrganisation } from '@/features/organisations/api'
import { apiRequest } from '@/lib/api'

import { newOrganiser, signInAs, staffAccount, uniqueEmail } from './backend'
import type { Credentials } from './backend'

/** A staff account read from two variables, or null when either is unset. */
export function optionalAccount(
  email: string | undefined,
  password: string | undefined,
): Credentials | null {
  if (email === undefined || email === '' || password === undefined || password === '') {
    return null
  }
  return { email, password }
}

export const LEAD = optionalAccount(
  import.meta.env.INTEGRATION_LEAD_EMAIL,
  import.meta.env.INTEGRATION_LEAD_PASSWORD,
)
export const VENUE_STAFF = optionalAccount(
  import.meta.env.INTEGRATION_VENUE_STAFF_EMAIL,
  import.meta.env.INTEGRATION_VENUE_STAFF_PASSWORD,
)

/** The account, which the test's skip condition has already checked is set. */
export function required(account: Credentials | null): Credentials {
  if (account === null) {
    throw new Error('This check needs an account that is not set; it should have been skipped.')
  }
  return account
}

/** A date `days` from now, as the backend reads dates ("2026-11-20"). */
function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 24 * 60 * 60_000).toISOString().slice(0, 10)
}

/** The day every event made here runs, 09:00 to 17:00. */
export const EVENT_DATE = daysFromNow(30)

/** As the staff account: record a client organisation, and sign a new organiser of it up. */
async function organiserOfNewOrganisation(): Promise<Credentials> {
  await signInAs(staffAccount())
  const organisation = await createOrganisation({
    name: `Integration organisation ${uniqueEmail('organisation')}`,
    contact_name: 'Integration Contact',
    contact_email: uniqueEmail('contact'),
  })
  const organiser = newOrganiser(organisation.id)
  await register(organiser)
  return { email: organiser.email, password: organiser.password }
}

/** A new organiser's submitted event request: the reference and name it was given. */
export async function submittedEvent(): Promise<{ reference: string; name: string }> {
  await signInAs(await organiserOfNewOrganisation())
  return apiRequest<{ reference: string; name: string }>('/api/events/requests', {
    method: 'POST',
    body: {
      name: `Integration Event ${uniqueEmail('event')}`,
      proposed_date: EVENT_DATE,
      end_date: EVENT_DATE,
      start_time: '09:00',
      end_time: '17:00',
      expected_attendance: 120,
      accessibility_needs: 'Step-free entrance',
    },
  })
}

/** As the staff account, the event's coordinator: POST to one of the event's actions. */
export async function coordinatorPosts(reference: string, action: string, body?: object) {
  await signInAs(staffAccount())
  await apiRequest(`/api/events/requests/${reference}/${action}`, { method: 'POST', body })
}

/** A submitted event, assigned by the Lead to the staff account, who reviews and approves it. */
export async function approvedEvent(): Promise<{ reference: string; name: string }> {
  const event = await submittedEvent()
  await signInAs(required(LEAD))
  await assignCoordinator({
    reference: event.reference,
    coordinator_email: staffAccount().email,
  })
  await coordinatorPosts(event.reference, 'review')
  await coordinatorPosts(event.reference, 'decide', { outcome: 'approved' })
  return event
}

/** As Venue Staff: add a venue for 300 that suits a theatre layout; answers its id. */
export async function newVenue(): Promise<number> {
  await signInAs(required(VENUE_STAFF))
  const venue = await apiRequest<{ id: number }>('/api/venues', {
    method: 'POST',
    body: {
      name: `Integration Hall ${uniqueEmail('venue')}`,
      location: 'Level 1',
      capacity: 300,
      supported_layouts: ['theatre'],
      facilities: ['projector'],
      accessibility_features: ['wheelchair_access'],
    },
  })
  return venue.id
}
