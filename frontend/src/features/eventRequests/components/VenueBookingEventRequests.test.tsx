import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-24 AC4, AC8, AC11: Venue Staff's Staff home lists every event with a venue booking
 * request or a booking (ADR-0085, ADR-0090). The rows come from the mock in
 * src/mocks/handlers/booking.ts.
 */

const LIST_NAME = 'Events with venue bookings'
const WITH_VENUE_BOOKINGS_PATH = '/api/events/requests/with-venue-bookings'

function openStaffHome(account: MockAccount) {
  return renderApp(ROUTES.STAFF_HOME, { session: mockSessionFor(account) })
}

async function venueBookingList(): Promise<HTMLElement> {
  return screen.findByRole('list', { name: LIST_NAME })
}

function rowFor(list: HTMLElement, reference: string): HTMLElement {
  const rows = within(list).getAllByRole('listitem')
  const row = rows.find((candidate) => candidate.textContent.includes(reference))
  if (row === undefined) {
    throw new Error(`No row for ${reference}`)
  }
  return row
}

describe('SCRUM-24 AC4 Staff home: the events with venue bookings, for Venue Staff', () => {
  it('lists every event with a booking request or booking, in the order the backend sends them', async () => {
    openStaffHome(MOCK_ACCOUNTS.venueStaff)

    const rows = within(await venueBookingList()).getAllByRole('listitem')
    const references = rows.map((row) => within(row).getByText(/^EVR-/).textContent)
    expect(references).toEqual([
      'EVR-BOOK0110',
      'EVR-BOOK0109',
      'EVR-BOOK0108',
      'EVR-BOOK0107',
      'EVR-BOOK0106',
      'EVR-BOOK0105',
      'EVR-BOOK0104',
    ])
  })

  it("shows each event's name, date, time, reference and status (AC8)", async () => {
    openStaffHome(MOCK_ACCOUNTS.venueStaff)

    const row = rowFor(await venueBookingList(), 'EVR-BOOK0105')
    expect(within(row).getByRole('heading', { name: 'Design Workshop' })).toBeInTheDocument()
    expect(row).toHaveTextContent('Fri, 20 Nov · 9:00 am – 5:00 pm')
    expect(row).toHaveTextContent('Approved')
  })

  it('opens nothing from a row, since Venue Staff have no page for one event yet (AC9)', async () => {
    openStaffHome(MOCK_ACCOUNTS.venueStaff)

    const list = await venueBookingList()

    expect(within(list).getAllByRole('listitem')).toHaveLength(7)
    expect(within(list).queryAllByRole('link')).toEqual([])
  })

  it("shows the backend's message when no event has a venue booking (AC11)", async () => {
    server.use(
      http.get(WITH_VENUE_BOOKINGS_PATH, () =>
        HttpResponse.json({
          event_requests: [],
          message: 'Nothing booked yet, from the backend.',
        }),
      ),
    )
    openStaffHome(MOCK_ACCOUNTS.venueStaff)

    expect(await screen.findByText('Nothing booked yet, from the backend.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: LIST_NAME })).not.toBeInTheDocument()
  })

  it("shows the backend's message when the list can't be read", async () => {
    server.use(
      http.get(WITH_VENUE_BOOKINGS_PATH, () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'The venue list is down for a moment.' },
          { status: 500 },
        ),
      ),
    )
    openStaffHome(MOCK_ACCOUNTS.venueStaff)

    expect(await screen.findByText('The venue list is down for a moment.')).toBeInTheDocument()
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
    ['Technical Support', MOCK_ACCOUNTS.technicalSupport],
    ['the Safety Officer', MOCK_ACCOUNTS.safetyOfficer],
  ])('shows %s no such list, and asks for none', async (_role, account) => {
    const requests = recordRequests()
    openStaffHome(account)

    expect(await screen.findByRole('heading', { level: 1, name: 'Staff home' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: LIST_NAME })).not.toBeInTheDocument()
    const asked = requests.map((request) => new URL(request.url).pathname)
    expect(asked).not.toContain(WITH_VENUE_BOOKINGS_PATH)
  })
})
