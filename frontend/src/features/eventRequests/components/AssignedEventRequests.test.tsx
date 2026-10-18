import { screen, within } from '@testing-library/react'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { recordRequests } from '@/test/recordRequests'
import { signedIn } from '@/store'
import { renderApp } from '@/test/render'

/**
 * SCRUM-24 AC2, AC8, AC9, AC11: an Event Coordinator's Staff home lists the events assigned to
 * them, each opening its record (ADR-0056). The rows come from the mock in
 * src/mocks/handlers/eventRequests.ts: Chloe has five; Daniel has none.
 */

const LIST_NAME = 'Your assigned events'

function openStaffHome(account: MockAccount) {
  return renderApp(ROUTES.STAFF_HOME, { session: mockSessionFor(account) })
}

async function assignedList(): Promise<HTMLElement> {
  return screen.findByRole('list', { name: LIST_NAME })
}

describe("SCRUM-24 AC2 Staff home: a coordinator's assigned events", () => {
  it('lists the events assigned to them, in the order the backend sends them', async () => {
    openStaffHome(MOCK_ACCOUNTS.coordinator)

    const headings = within(await assignedList()).getAllByRole('heading')
    expect(headings.map((heading) => heading.textContent)).toEqual([
      'Partner Summit',
      'Harbourfront Careers Fair',
      'Evening Product Showcase',
      'Year-End Town Hall',
      'Customer Roadshow',
    ])
  })

  it("shows each event's date, time and status (AC8)", async () => {
    openStaffHome(MOCK_ACCOUNTS.coordinator)

    const row = within(await assignedList()).getAllByRole('listitem')[1]
    expect(row).toHaveTextContent('Tue, 10 Nov · 9:00 am – 5:00 pm')
    expect(row).toHaveTextContent('Approved')
  })

  it("opens each event's record at the coordinator's address (AC9)", async () => {
    openStaffHome(MOCK_ACCOUNTS.coordinator)

    const links = within(await assignedList()).getAllByRole('link')
    expect(links[0]).toHaveAttribute('href', '/events/EVR-7K2M9QXA')
    expect(links[1]).toHaveAttribute('href', '/events/EVR-BOOK0101')
  })

  it("shows the backend's message to a coordinator with no events (AC11)", async () => {
    openStaffHome(MOCK_ACCOUNTS.freshCoordinator)

    expect(
      await screen.findByText('No event requests are assigned to you yet.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: LIST_NAME })).not.toBeInTheDocument()
  })

  it("reads the list again for the next coordinator to sign in, never showing the last one's", async () => {
    const { store } = openStaffHome(MOCK_ACCOUNTS.coordinator)
    await assignedList()

    store.dispatch(signedIn(mockSessionFor(MOCK_ACCOUNTS.freshCoordinator)))

    expect(
      await screen.findByText('No event requests are assigned to you yet.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Partner Summit' })).not.toBeInTheDocument()
  })

  it.each([
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
    ['Technical Support', MOCK_ACCOUNTS.technicalSupport],
  ])('shows %s no assigned list, and asks for none', async (_role, account) => {
    const requests = recordRequests()
    openStaffHome(account)

    expect(await screen.findByRole('heading', { level: 1, name: 'Staff home' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: LIST_NAME })).not.toBeInTheDocument()
    const asked = requests.map((request) => new URL(request.url).pathname)
    expect(asked).not.toContain('/api/events/requests/assigned')
  })
})
