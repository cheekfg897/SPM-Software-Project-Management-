import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { venueRequestsPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { MOCK_ARRANGEMENTS, MOCK_BOOKING_EVENTS } from '@/mocks/handlers/bookingFixtures'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'

import type { BookingRequest } from '../api'

/**
 * SCRUM-92: an arrangement whose venue became unavailable is flagged by the backend. The
 * coordinator sees why under it, with the original booking still shown.
 */

const SESSION = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }
const BOOKING_URL = '/api/venues/events/:reference/booking-requests'
const { bookedHall, bookedSideRoom, reviewedAuditorium } = MOCK_ARRANGEMENTS
const BOOKED_EVENT = MOCK_BOOKING_EVENTS.booked
const CAUSES_LABEL = 'Why its venue is unavailable'

function openEvent(reference: string) {
  return renderApp(venueRequestsPath(reference), SESSION)
}

/** Answer the booked event's list with these arrangements instead of the mock's own. */
function listBookedEventAs(arrangements: BookingRequest[]) {
  server.use(http.get(BOOKING_URL, () => HttpResponse.json(arrangements)))
}

function item(purpose: string): Promise<HTMLElement> {
  return screen.findByRole('listitem', { name: purpose })
}

/** Each cause listed under the arrangement, as its text. */
async function causesUnder(purpose: string): Promise<string[]> {
  const causes = within(await item(purpose)).getByRole('list', { name: CAUSES_LABEL })
  return within(causes)
    .getAllByRole('listitem')
    .map((cause) => cause.textContent)
}

describe('SCRUM-92 why an arrangement needs an alternative venue', () => {
  it('names the block’s category, its note and its period in business time (AC1, AC2)', async () => {
    openEvent(BOOKED_EVENT.reference)

    expect(await causesUnder(bookedHall.purpose)).toEqual([
      'Maintenance: Roof repairs. Unavailable from 26 Nov, 8:00 am to 26 Nov, 6:00 pm.',
    ])
  })

  it('says a deactivated venue is unavailable until it is reactivated (AC9)', async () => {
    openEvent(MOCK_BOOKING_EVENTS.inSafetyReview.reference)

    expect(await causesUnder(reviewedAuditorium.purpose)).toEqual([
      'Renovation: Closed for refit. Unavailable from 1 Nov, 12:00 pm until the venue is reactivated.',
    ])
  })

  it('lists every block that flagged it, in the backend’s order', async () => {
    listBookedEventAs([
      {
        ...bookedHall,
        unavailability: [
          ...bookedHall.unavailability,
          {
            category: 'equipment_failure',
            reason: 'Lift broken',
            starts_at: '2026-11-26T12:00:00+08:00',
            ends_at: '2026-11-27T09:00:00+08:00',
          },
        ],
      },
    ])

    openEvent(BOOKED_EVENT.reference)

    expect(await causesUnder(bookedHall.purpose)).toEqual([
      'Maintenance: Roof repairs. Unavailable from 26 Nov, 8:00 am to 26 Nov, 6:00 pm.',
      'Equipment failure: Lift broken. Unavailable from 26 Nov, 12:00 pm to 27 Nov, 9:00 am.',
    ])
  })

  it('keeps the original booking and its details on show (AC4)', async () => {
    openEvent(BOOKED_EVENT.reference)

    const hall = await item(bookedHall.purpose)
    expect(hall).toHaveTextContent('Approved')
    expect(hall).toHaveTextContent('Venue 1 · 26 Nov, 1:00 pm – 5:00 pm')
    expect(hall).toHaveTextContent('Reason: Booked')
  })

  it('shows nothing of the kind for an arrangement that is not flagged', async () => {
    openEvent(BOOKED_EVENT.reference)

    const sideRoom = await item(bookedSideRoom.purpose)
    expect(sideRoom).not.toHaveTextContent('alternative venue')
    expect(within(sideRoom).queryByRole('list', { name: CAUSES_LABEL })).not.toBeInTheDocument()
  })

  it('drops the flag once the backend clears it, and the original booking stands (AC8)', async () => {
    listBookedEventAs([{ ...bookedHall, needs_alternative_venue: false, unavailability: [] }])

    openEvent(BOOKED_EVENT.reference)

    const hall = await item(bookedHall.purpose)
    expect(hall).toHaveTextContent('Approved')
    expect(hall).not.toHaveTextContent('alternative venue')
  })

  it('shows a released arrangement as Released, with no flag, though the backend keeps why (AC7)', async () => {
    listBookedEventAs([{ ...bookedHall, status: 'released', needs_alternative_venue: false }])

    openEvent(BOOKED_EVENT.reference)

    const hall = await item(bookedHall.purpose)
    expect(hall).toHaveTextContent('Released')
    expect(hall).not.toHaveTextContent('alternative venue')
    expect(within(hall).queryByRole('button')).not.toBeInTheDocument()
  })
})
