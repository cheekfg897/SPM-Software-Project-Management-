/**
 * Helpers that take an event through the real backend to the point a check needs: submitted by
 * a new organiser, assigned by a Lead and approved by the staff account (an Event Coordinator),
 * then given venues by Venue Staff, sent to Safety Review and approved by the Safety Officer.
 * The Lead, Venue Staff and Safety Officer accounts are optional: they come from
 * INTEGRATION_LEAD_*, INTEGRATION_VENUE_STAFF_* and INTEGRATION_SAFETY_OFFICER_*, and the checks
 * that need them skip without them. CI makes all three (frontend.yml).
 */

import { register } from '@/features/auth/api'
import { decideBookingRequest, raiseBookingRequest } from '@/features/booking/api'
import { fetchCatalogue } from '@/features/catalogue/api'
import { confirmEvent, updateRegistrationSettings } from '@/features/eventRequests/api'
import { assignCoordinator } from '@/features/lead/api'
import { createOrganisation } from '@/features/organisations/api'
import { recordSafetyOutcome } from '@/features/safety/api'
import type { SafetyChecklist } from '@/features/safety/api'
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
export const SAFETY_OFFICER = optionalAccount(
  import.meta.env.INTEGRATION_SAFETY_OFFICER_EMAIL,
  import.meta.env.INTEGRATION_SAFETY_OFFICER_PASSWORD,
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

/** An event made here: the reference and name it was given, and the organiser who asked for it. */
export interface PlannedEvent {
  reference: string
  name: string
  organiser: Credentials
}

/** A new organiser's submitted event request. Leaves the organiser signed in. */
export async function submittedEvent(): Promise<PlannedEvent> {
  const organiser = await organiserOfNewOrganisation()
  await signInAs(organiser)
  const submitted = await apiRequest<{ reference: string; name: string }>('/api/events/requests', {
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
  return { reference: submitted.reference, name: submitted.name, organiser }
}

/** As the staff account, the event's coordinator: POST to one of the event's actions. */
export async function coordinatorPosts(reference: string, action: string, body?: object) {
  await signInAs(staffAccount())
  await apiRequest(`/api/events/requests/${reference}/${action}`, { method: 'POST', body })
}

/** A submitted event, assigned by the Lead to the staff account. Leaves the Lead signed in. */
export async function assignedEvent(): Promise<PlannedEvent> {
  const event = await submittedEvent()
  await signInAs(required(LEAD))
  await assignCoordinator({
    reference: event.reference,
    coordinator_email: staffAccount().email,
  })
  return event
}

/** A submitted event, assigned by the Lead to the staff account, who reviews and approves it. */
export async function approvedEvent(): Promise<PlannedEvent> {
  const event = await assignedEvent()
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

/** A note on each of SCRUM-98 AC2's seven items. */
export const CHECKLIST: SafetyChecklist = {
  attendance_vs_capacity: '120 expected in a hall for 300.',
  venue_layout: 'Theatre layout, aisles clear.',
  emergency_access: 'Two exits, both signed.',
  accessibility: 'Step-free entrance confirmed.',
  equipment_placement: 'No equipment requested.',
  crowd_movement: 'One-way flow at the doors.',
  venue_restrictions: 'No open flames.',
}

/**
 * An approved event with one venue booked and approved, as the staff account's to send: its
 * reference, its name, the venue's id and the booking's id.
 */
export async function eventReadyForSafetyReview() {
  const event = await approvedEvent()
  const venueId = await newVenue()
  await signInAs(staffAccount())
  const booking = await raiseBookingRequest(event.reference, {
    venue_id: venueId,
    starts_at: `${EVENT_DATE}T09:00:00+08:00`,
    ends_at: `${EVENT_DATE}T12:00:00+08:00`,
    purpose: 'Integration safety check',
  })
  await signInAs(required(VENUE_STAFF))
  await decideBookingRequest(booking.id, { outcome: 'approved' })
  return { ...event, venueId, bookingId: booking.id }
}

/**
 * An event the Safety Officer has approved, in Safety Review, with its one approved booking:
 * what Venue Staff and Technical Support may prepare (SCRUM-84, SCRUM-85 AC5).
 */
export async function safetyApprovedEvent() {
  const event = await eventReadyForSafetyReview()
  await coordinatorPosts(event.reference, 'safety-review')
  await signInAs(required(SAFETY_OFFICER))
  await recordSafetyOutcome({
    reference: event.reference,
    outcome: 'approved',
    checklist: CHECKLIST,
  })
  return event
}

/**
 * A Safety-approved event the staff account confirmed and opened for registration, with 50
 * places (SCRUM-49, SCRUM-69): what an Attendee registers for. Also its id, which the
 * registration routes take, read from the catalogue. Leaves the staff account signed in.
 */
export async function registrableEvent() {
  const event = await safetyApprovedEvent()
  await signInAs(staffAccount())
  await confirmEvent(event.reference)
  await updateRegistrationSettings(event.reference, {
    registration_enabled: true,
    registration_capacity: 50,
  })
  const page = await fetchCatalogue({ q: event.name })
  const listed = page.items.find((item) => item.reference === event.reference)
  if (listed === undefined) {
    throw new Error(`The catalogue does not list ${event.reference} once it is open.`)
  }
  return { ...event, id: listed.id }
}
