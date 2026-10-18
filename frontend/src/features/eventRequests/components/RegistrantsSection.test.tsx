import { screen, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import { coordinatorEventPath, organiserRequestPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'

import { findRegion } from '../test/recordPage'

/**
 * SCRUM-55: who has registered for an event, on its record, for its coordinator and for an
 * organiser of its organisation, with the count against the capacity (ADR-0076). The mock
 * (src/mocks/handlers/eventRecordSections.ts) has three registrants, one who withdrew (SCRUM-53)
 * and 80 places for Chloe's EVR-BOOK0102, in Sara's organisation, and nobody and no capacity
 * for EVR-7K2M9QXA.
 */

const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
const SARA = mockSessionFor(MOCK_ACCOUNTS.otherOrganiser)
const ORGANISER = mockSessionFor(MOCK_ACCOUNTS.organiser)
const TOWN_HALL = 'EVR-BOOK0102'
const REGISTRANTS_PATH = `/api/events/requests/${TOWN_HALL}/registrations`

/** Each registrant's row, as the text of its cells. */
async function registrantRows(): Promise<string[][]> {
  const registrants = await findRegion('Registrants')
  const table = await within(registrants).findByRole('table', { name: 'Registrants' })
  const rows = within(table).getAllByRole('row').slice(1)
  return rows.map((row) =>
    within(row)
      .getAllByRole('cell')
      .map((cell) => cell.textContent),
  )
}

describe('SCRUM-55 registrants on an event record', () => {
  it("shows the coordinator each registrant's name, email, date and status, oldest first (AC2, AC3)", async () => {
    renderApp(coordinatorEventPath(TOWN_HALL), { session: COORDINATOR })

    expect(await registrantRows()).toEqual([
      ['Hannah Lee', 'hannah.lee@example.com', '6 Oct, 9:15 am', 'Registered'],
      ['Owen Teo', 'owen.teo@example.com', '7 Oct, 8:00 am', 'Withdrawn'],
      ['Ravi Kumar', 'ravi.kumar@example.com', '7 Oct, 6:40 pm', 'Registered'],
      ['Mei Ling Tan', 'meiling.tan@example.com', '8 Oct, 12:05 pm', 'Registered'],
    ])
  })

  it('counts those still registered against the capacity, with the places left (AC4)', async () => {
    renderApp(coordinatorEventPath(TOWN_HALL), { session: COORDINATOR })

    const registrants = await findRegion('Registrants')

    expect(
      await within(registrants).findByText('3 registered of 80 places · 77 left'),
    ).toBeInTheDocument()
  })

  it("shows an organiser of the event's organisation the same list (AC1)", async () => {
    renderApp(organiserRequestPath(TOWN_HALL), { session: SARA })

    const rows = await registrantRows()

    expect(rows.map(([name]) => name)).toEqual([
      'Hannah Lee',
      'Owen Teo',
      'Ravi Kumar',
      'Mei Ling Tan',
    ])
  })

  it('says when nobody has registered and no capacity is set yet', async () => {
    renderApp(organiserRequestPath('EVR-7K2M9QXA'), { session: ORGANISER })

    const registrants = await findRegion('Registrants')

    expect(await within(registrants).findByText('No one has registered yet.')).toBeInTheDocument()
    expect(within(registrants).getByText('0 registered · no capacity set yet')).toBeInTheDocument()
    expect(within(registrants).queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows the numbers the backend sends, not ones it works out', async () => {
    server.use(
      http.get(REGISTRANTS_PATH, () =>
        HttpResponse.json({ capacity: 5, registered_count: 7, places_left: 0, items: [] }),
      ),
    )
    renderApp(coordinatorEventPath(TOWN_HALL), { session: COORDINATOR })

    const registrants = await findRegion('Registrants')

    expect(
      await within(registrants).findByText('7 registered of 5 places · 0 left'),
    ).toBeInTheDocument()
  })

  it("shows the backend's message when the list can't be read, and the record still", async () => {
    server.use(
      http.get(REGISTRANTS_PATH, () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'Registrations are unavailable right now.' },
          { status: 500 },
        ),
      ),
    )
    renderApp(coordinatorEventPath(TOWN_HALL), { session: COORDINATOR })

    const registrants = await findRegion('Registrants')

    expect(await within(registrants).findByRole('alert')).toHaveTextContent(
      'Registrations are unavailable right now.',
    )
    expect(screen.getByRole('region', { name: 'About the event' })).toBeInTheDocument()
  })

  it('says it is loading while the list is on its way', async () => {
    server.use(
      http.get(REGISTRANTS_PATH, async () => {
        await delay('infinite')
      }),
    )
    renderApp(coordinatorEventPath(TOWN_HALL), { session: COORDINATOR })

    const registrants = await findRegion('Registrants')

    expect(within(registrants).getByRole('status')).toHaveTextContent('Loading the registrants')
  })
})
