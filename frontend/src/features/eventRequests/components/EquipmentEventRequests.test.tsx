import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-24 AC5, AC8, AC11: Technical Support's Staff home lists every event with an equipment
 * request, each opening its Equipment page (ADR-0061). The rows come from the mock in
 * src/mocks/handlers/techSupport.ts.
 */

const LIST_NAME = 'Events with equipment'
const WITH_EQUIPMENT_PATH = '/api/events/requests/with-equipment'

function openStaffHome(account: MockAccount) {
  return renderApp(ROUTES.STAFF_HOME, { session: mockSessionFor(account) })
}

async function equipmentList(): Promise<HTMLElement> {
  return screen.findByRole('list', { name: LIST_NAME })
}

describe('SCRUM-24 AC5 Staff home: the events with equipment, for Technical Support', () => {
  it('lists every event with an equipment request, in the order the backend sends them', async () => {
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    const headings = within(await equipmentList()).getAllByRole('heading')
    expect(headings.map((heading) => heading.textContent)).toEqual([
      'Long-Service Awards',
      'Rooftop Film Night',
      'Partner Summit',
      'Graduation Dinner',
      'Harbourfront Careers Fair',
      'Sunrise Wellness Walk',
      'Product Launch Evening',
      'Evening Product Showcase',
      'Board Breakfast Briefing',
      'Charity Fun Run',
      'Data Science Meetup',
      'Year-End Town Hall',
    ])
  })

  it("shows each event's date, time, reference and status, and no attendance it wasn't sent (AC8)", async () => {
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    const row = within(await equipmentList()).getAllByRole('listitem')[0]
    expect(row).toHaveTextContent('Sun, 4 Oct · 6:00 pm – 9:00 pm')
    expect(row).toHaveTextContent('EVR-TECH0007')
    expect(row).toHaveTextContent('Confirmed')
    expect(row).not.toHaveTextContent('expected')
  })

  it("opens each event's Equipment page, which Technical Support may open", async () => {
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    const list = await equipmentList()
    expect(within(list).getAllByRole('link')[0]).toHaveAttribute(
      'href',
      '/events/EVR-TECH0007/equipment',
    )
    expect(within(list).getByRole('link', { name: /Evening Product Showcase/ })).toHaveAttribute(
      'href',
      '/events/EVR-MOCK0001/equipment',
    )
  })

  it("shows the backend's message when no event has equipment (AC11)", async () => {
    server.use(
      http.get(WITH_EQUIPMENT_PATH, () =>
        HttpResponse.json({
          event_requests: [],
          message: 'Nothing to see here, from the backend.',
        }),
      ),
    )
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    expect(await screen.findByText('Nothing to see here, from the backend.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: LIST_NAME })).not.toBeInTheDocument()
  })

  it("shows the backend's message when the list can't be read", async () => {
    server.use(
      http.get(WITH_EQUIPMENT_PATH, () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'The equipment list is down for a moment.' },
          { status: 500 },
        ),
      ),
    )
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    expect(await screen.findByText('The equipment list is down for a moment.')).toBeInTheDocument()
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ])('shows %s no such list, and asks for none', async (_role, account) => {
    const requests = recordRequests()
    openStaffHome(account)

    expect(await screen.findByRole('heading', { level: 1, name: 'Staff home' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: LIST_NAME })).not.toBeInTheDocument()
    const asked = requests.map((request) => new URL(request.url).pathname)
    expect(asked).not.toContain(WITH_EQUIPMENT_PATH)
  })
})
