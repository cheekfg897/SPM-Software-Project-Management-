import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'

const TYPES_URL = '/api/equipment/types'

/** Staff who may read the catalogue but not change it (SCRUM-27 AC3). */
const OTHER_STAFF: [string, MockAccount][] = [
  ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
  ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
  ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
]
const EVERY_STAFF_ROLE: [string, MockAccount][] = [
  ...OTHER_STAFF,
  ['Technical Support', MOCK_ACCOUNTS.technicalSupport],
]
const EXTERNAL: [string, MockAccount][] = [
  ['an Attendee', MOCK_ACCOUNTS.attendee],
  ['an Event Organiser', MOCK_ACCOUNTS.organiser],
]

function openCatalogueAs(account: MockAccount) {
  return renderApp(ROUTES.EQUIPMENT_CATALOGUE, { session: mockSessionFor(account) })
}

async function findTable() {
  return screen.findByRole('table', { name: 'Equipment types' })
}

/** The table's rows below the header, each as the text of its cells. */
async function rowTexts() {
  const rows = within(await findTable())
    .getAllByRole('row')
    .slice(1)
  return rows.map((row) =>
    within(row)
      .getAllByRole('cell')
      .map((cell) => cell.textContent),
  )
}

function headerLink() {
  return within(screen.getByRole('banner')).queryByRole('link', { name: 'Equipment' })
}

describe('SCRUM-27 the equipment catalogue page', () => {
  it('lists every type with its description, total held and where it is kept (AC2)', async () => {
    openCatalogueAs(MOCK_ACCOUNTS.coordinator)

    expect(await rowTexts()).toEqual([
      ['Lectern', 'No description', '2', 'Store: Main store'],
      ['Microphone', 'Wireless, handheld.', '12', 'Venue 3'],
      ['Projector', 'Full HD, with HDMI and USB-C.', '10', 'Store: Main store'],
    ])
  })

  it("keeps the backend's order rather than sorting for itself", async () => {
    server.use(
      http.get(TYPES_URL, () =>
        HttpResponse.json([
          {
            id: 41,
            name: 'Zip ties',
            description: null,
            total_quantity: 500,
            venue_id: null,
            store_name: 'Jurong store',
          },
          {
            id: 42,
            name: 'Amplifier',
            description: null,
            total_quantity: 3,
            venue_id: 6,
            store_name: null,
          },
        ]),
      ),
    )
    openCatalogueAs(MOCK_ACCOUNTS.coordinator)

    const names = (await rowTexts()).map((cells) => cells[0])
    expect(names).toEqual(['Zip ties', 'Amplifier'])
  })

  it("links each type's name to its own page", async () => {
    openCatalogueAs(MOCK_ACCOUNTS.coordinator)

    const table = within(await findTable())
    expect(table.getByRole('link', { name: 'Microphone' })).toHaveAttribute(
      'href',
      '/staff/equipment/2',
    )
  })

  it.each(EVERY_STAFF_ROLE)('lets %s open it from the header (AC3)', async (_who, account) => {
    const { user, router } = renderApp(ROUTES.HOME, { session: mockSessionFor(account) })

    await user.click(headerLink() ?? expect.fail('no Equipment link in the header'))

    expect(router.state.location.pathname).toBe(ROUTES.EQUIPMENT_CATALOGUE)
    expect(await findTable()).toBeInTheDocument()
  })

  it.each(EXTERNAL)('gives %s no header link and sends them away', (_who, account) => {
    const { router } = openCatalogueAs(account)

    expect(router.state.location.pathname).not.toBe(ROUTES.EQUIPMENT_CATALOGUE)
    expect(headerLink()).not.toBeInTheDocument()
  })

  it('sends a visitor to the staff log-in page', () => {
    const { router } = renderApp(ROUTES.EQUIPMENT_CATALOGUE)

    expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN)
    expect(headerLink()).not.toBeInTheDocument()
  })

  it('offers Technical Support a link to add a type (AC1)', async () => {
    openCatalogueAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await screen.findByRole('link', { name: 'Add equipment type' })).toHaveAttribute(
      'href',
      ROUTES.NEW_EQUIPMENT_TYPE,
    )
  })

  it.each(OTHER_STAFF)('offers %s no link to add a type (AC3)', async (_who, account) => {
    openCatalogueAs(account)

    await findTable()
    expect(screen.queryByRole('link', { name: 'Add equipment type' })).not.toBeInTheDocument()
  })

  it('says what it is loading', () => {
    openCatalogueAs(MOCK_ACCOUNTS.coordinator)

    expect(screen.getByRole('status')).toHaveTextContent('Loading the equipment catalogue')
  })

  it('says so when the catalogue is empty', async () => {
    server.use(http.get(TYPES_URL, () => HttpResponse.json([])))
    openCatalogueAs(MOCK_ACCOUNTS.coordinator)

    expect(await screen.findByText('No equipment types yet.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it("shows the backend's message when the catalogue can't be read", async () => {
    server.use(
      http.get(TYPES_URL, () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'The catalogue is resting.' },
          { status: 500 },
        ),
      ),
    )
    openCatalogueAs(MOCK_ACCOUNTS.coordinator)

    expect(await screen.findByRole('alert')).toHaveTextContent('The catalogue is resting.')
  })
})
