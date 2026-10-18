import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { INTERNAL_ROLES } from '@/config/roles'
import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { errorResponse } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-66: staff record client organisations and see them listed, so they can give an Event
 * Organiser the organisation ID sign-up asks for. Attendees and organisers never see them (AC5).
 */

const ORGANISATIONS_URL = '/api/organisations'
const STAFF = [
  MOCK_ACCOUNTS.coordinator,
  MOCK_ACCOUNTS.lead,
  MOCK_ACCOUNTS.venueStaff,
  MOCK_ACCOUNTS.technicalSupport,
  MOCK_ACCOUNTS.safetyOfficer,
]

type AppView = ReturnType<typeof renderApp>

function openAs(account: MockAccount): AppView {
  return renderApp(ROUTES.ORGANISATIONS, { session: mockSessionFor(account) })
}

async function tableRows(): Promise<string[][]> {
  const table = await screen.findByRole('table', { name: 'Client organisations' })
  const rows = within(table).getAllByRole('row').slice(1)
  return rows.map((row) =>
    within(row)
      .getAllByRole('cell')
      .map((cell) => cell.textContent ?? ''),
  )
}

/** Type into a field from scratch: after a form reset, user-event still remembers the old text. */
async function typeInto(view: AppView, label: string, text: string) {
  const field = await view.findByLabelText(label)
  await view.user.clear(field)
  await view.user.type(field, text)
}

async function fillOrganisation(view: AppView, name: string) {
  await typeInto(view, 'Organisation name', name)
  await typeInto(view, 'Contact name', 'Wei Ling Tan')
  await typeInto(view, 'Contact email', 'weiling@bayfront.test')
}

function recordButton(view: AppView) {
  return view.getByRole('button', { name: 'Record organisation' })
}

describe('SCRUM-66 client organisations page', () => {
  it('tries every staff role, so a role left out of the page or the link shows', () => {
    expect(STAFF.map((account) => account.role).sort()).toEqual([...INTERNAL_ROLES].sort())
  })

  it('lists each organisation with its ID and contact details, in the backend’s order', async () => {
    openAs(MOCK_ACCOUNTS.venueStaff)

    expect(await tableRows()).toEqual([
      ['3', 'Acme Conferences', 'Siti Rahman', 'siti@acmeconf.test', '6234-5678'],
      ['2', 'Harbour Lights Ltd', 'Marcus Lee', 'marcus@harbourlights.test', 'Not given'],
      ['1', 'Orchid Events Co', 'Priya Nair', 'priya@orchidevents.test', '+65 6123 4567'],
    ])
  })

  it('says what is loading while the list is read', () => {
    openAs(MOCK_ACCOUNTS.venueStaff)

    expect(screen.getByText('Loading client organisations')).toBeInTheDocument()
  })

  it('says so when there are no organisations yet', async () => {
    server.use(http.get(ORGANISATIONS_URL, () => HttpResponse.json({ organisations: [] })))

    openAs(MOCK_ACCOUNTS.venueStaff)

    expect(await screen.findByText('No client organisations yet.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows the backend’s message when the list cannot be read', async () => {
    server.use(
      http.get(ORGANISATIONS_URL, () =>
        errorResponse(503, 'service_unavailable', 'The organisations are resting.'),
      ),
    )

    openAs(MOCK_ACCOUNTS.venueStaff)

    expect(await screen.findByRole('alert')).toHaveTextContent('The organisations are resting.')
  })

  it.each(STAFF)('lets $role open the page', async (account) => {
    const { router } = openAs(account)

    expect(await tableRows()).toHaveLength(3)
    expect(router.state.location.pathname).toBe(ROUTES.ORGANISATIONS)
  })

  it.each([
    { account: MOCK_ACCOUNTS.attendee, home: ROUTES.MY_EVENTS },
    { account: MOCK_ACCOUNTS.organiser, home: ROUTES.ORGANISER_HOME },
  ])('sends $account.role to $home, asking the backend for nothing', async ({ account, home }) => {
    const requests = recordRequests()

    const { router } = openAs(account)

    await waitFor(() => expect(router.state.location.pathname).toBe(home))
    expect(requests.filter((request) => request.url.includes(ORGANISATIONS_URL))).toEqual([])
  })

  it('sends a visitor to the staff log-in page, remembering the page', async () => {
    const { router } = renderApp(ROUTES.ORGANISATIONS)

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN))
    expect(router.state.location.search).toContain(encodeURIComponent(ROUTES.ORGANISATIONS))
  })

  it('records an organisation, says its ID, and lists it where the backend puts it', async () => {
    const requests = recordRequests()
    const view = openAs(MOCK_ACCOUNTS.coordinator)
    await fillOrganisation(view, 'Bayfront Partners')

    await view.user.click(recordButton(view))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Recorded Bayfront Partners. Its organisation ID is 4: give it to the organisation’s Event Organisers so they can sign up.',
    )
    await waitFor(async () => expect((await tableRows())[1]?.[1]).toBe('Bayfront Partners'))
    const post = requests.find((request) => request.method === 'POST')
    expect(await post?.json()).toEqual({
      name: 'Bayfront Partners',
      contact_name: 'Wei Ling Tan',
      contact_email: 'weiling@bayfront.test',
    })
    expect(view.getByLabelText('Organisation name')).toHaveValue('')
  })

  it('sends the contact phone when one is typed', async () => {
    const requests = recordRequests()
    const view = openAs(MOCK_ACCOUNTS.coordinator)
    await fillOrganisation(view, 'Bayfront Partners')
    await view.user.type(view.getByLabelText('Contact phone'), '+65 6555 0101')

    await view.user.click(recordButton(view))

    await screen.findByRole('status')
    const post = requests.find((request) => request.method === 'POST')
    expect(await post?.json()).toMatchObject({ contact_phone: '+65 6555 0101' })
  })

  it('shows the backend’s message against each field it refuses', async () => {
    const view = openAs(MOCK_ACCOUNTS.coordinator)
    await fillOrganisation(view, '   ')
    await view.user.type(view.getByLabelText('Contact phone'), '12345')

    await view.user.click(recordButton(view))

    expect(await view.findByLabelText('Organisation name')).toHaveAccessibleDescription(
      'Must not be blank.',
    )
    expect(view.getByLabelText('Contact phone')).toHaveAccessibleDescription(
      'Contact phone must have at least 7 digits and use only spaces, hyphens, brackets and a leading +.',
    )
    expect(view.getByLabelText('Contact name')).toHaveAccessibleDescription('')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows the backend’s refusal of a name already recorded', async () => {
    const view = openAs(MOCK_ACCOUNTS.coordinator)
    await fillOrganisation(view, 'Acme Conferences')

    await view.user.click(recordButton(view))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A client organisation with this name already exists.',
    )
    expect(view.getByLabelText('Organisation name')).toHaveValue('Acme Conferences')
  })

  it('forgets the last confirmation once another organisation is refused', async () => {
    const view = openAs(MOCK_ACCOUNTS.coordinator)
    await fillOrganisation(view, 'Bayfront Partners')
    await view.user.click(recordButton(view))
    await screen.findByRole('status')
    await waitFor(() => expect(view.getByLabelText('Organisation name')).toHaveValue(''))
    await fillOrganisation(view, 'Bayfront Partners')

    await view.user.click(recordButton(view))

    await screen.findByRole('alert')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it.each(STAFF)('shows $role a Clients link in the header', async (account) => {
    openAs(account)

    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Clients' })).toHaveAttribute(
      'href',
      ROUTES.ORGANISATIONS,
    )
    await tableRows()
  })

  it.each([MOCK_ACCOUNTS.attendee, MOCK_ACCOUNTS.organiser])(
    'shows $role no Clients link',
    async (account) => {
      renderApp(ROUTES.EVENTS, { session: mockSessionFor(account) })

      const nav = screen.getByRole('navigation', { name: 'Main' })
      expect(within(nav).queryByRole('link', { name: 'Clients' })).not.toBeInTheDocument()
      await screen.findByRole('heading', { level: 1 })
    },
  )
})
