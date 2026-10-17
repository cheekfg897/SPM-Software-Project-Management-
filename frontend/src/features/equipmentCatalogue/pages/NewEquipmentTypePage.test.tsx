import { screen, waitFor } from '@testing-library/react'
import { http } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { DUPLICATE_NAME_MESSAGE, NO_LOCATION_MESSAGE } from '@/mocks/handlers/equipmentCatalogue'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { OTHER_STAFF } from '../test/staff'
import { bodySent, FIELD, fillIn } from '../test/equipmentTypeForm'

function openFormAs(account: MockAccount) {
  return renderApp(ROUTES.NEW_EQUIPMENT_TYPE, { session: mockSessionFor(account) })
}

function openForm() {
  return openFormAs(MOCK_ACCOUNTS.technicalSupport)
}

async function save(user: ReturnType<typeof openForm>['user']) {
  await user.click(screen.getByRole('button', { name: 'Add equipment type' }))
}

describe('SCRUM-27 adding an equipment type', () => {
  it('sends what was typed and opens the new type, as the backend saved it (AC1)', async () => {
    const requests = recordRequests()
    const { user, router } = openForm()

    await fillIn(user, {
      [FIELD.NAME]: ' Folding table ',
      [FIELD.DESCRIPTION]: 'Oak, with a reading light.',
      [FIELD.TOTAL]: '2',
      [FIELD.STORE]: 'Jurong store',
    })
    await save(user)

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Folding table' }),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/staff/equipment/4')
    expect(screen.getByText('Store: Jurong store')).toBeInTheDocument()
    expect(await bodySent(requests, 'POST')).toEqual({
      name: ' Folding table ',
      description: 'Oak, with a reading light.',
      total_quantity: 2,
      venue_id: null,
      store_name: 'Jurong store',
    })
  })

  it('sends a venue by its number, and an empty description as empty', async () => {
    const requests = recordRequests()
    const { user } = openForm()

    await fillIn(user, { [FIELD.NAME]: 'Stage light', [FIELD.TOTAL]: '0', [FIELD.VENUE]: '8' })
    await save(user)

    expect(await screen.findByText('Venue 8')).toBeInTheDocument()
    expect(await bodySent(requests, 'POST')).toEqual({
      name: 'Stage light',
      description: '',
      total_quantity: 0,
      venue_id: 8,
      store_name: null,
    })
  })

  it("shows the backend's message under each field it refused, and stays on the form", async () => {
    const { user, router } = openForm()

    await fillIn(user, { [FIELD.NAME]: '   ', [FIELD.TOTAL]: '-1' })
    await save(user)

    await waitFor(() =>
      expect(screen.getByLabelText(FIELD.NAME)).toHaveAccessibleDescription('Must not be blank.'),
    )
    expect(screen.getByLabelText(FIELD.TOTAL)).toHaveAccessibleDescription(
      'Total quantity cannot be negative.',
    )
    expect(screen.getByLabelText(FIELD.NAME)).toBeInvalid()
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid request.')
    expect(router.state.location.pathname).toBe(ROUTES.NEW_EQUIPMENT_TYPE)
  })

  it('shows a refusal of the place under the venue number, where the backend puts it', async () => {
    const { user } = openForm()

    await fillIn(user, { [FIELD.NAME]: 'Folding table', [FIELD.TOTAL]: '2' })
    await save(user)

    await waitFor(() =>
      expect(screen.getByLabelText(FIELD.VENUE)).toHaveAccessibleDescription(NO_LOCATION_MESSAGE),
    )
  })

  it("shows the backend's message under the store name", async () => {
    const { user } = openForm()

    await fillIn(user, { [FIELD.NAME]: 'Folding table', [FIELD.TOTAL]: '2', [FIELD.STORE]: '  ' })
    await save(user)

    await waitFor(() =>
      expect(screen.getByLabelText(FIELD.STORE)).toHaveAccessibleDescription('Must not be blank.'),
    )
  })

  it("shows the backend's message for a name another type has", async () => {
    const { user } = openForm()

    await fillIn(user, { [FIELD.NAME]: 'Projector', [FIELD.TOTAL]: '2', [FIELD.VENUE]: '1' })
    await save(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(DUPLICATE_NAME_MESSAGE)
  })

  it('shows the button as busy while the backend saves', async () => {
    server.use(http.post('/api/equipment/types', () => new Promise<never>(() => undefined)))
    const { user } = openForm()

    await fillIn(user, { [FIELD.NAME]: 'Folding table', [FIELD.TOTAL]: '2', [FIELD.VENUE]: '1' })
    await save(user)

    expect(screen.getByRole('button', { name: 'Add equipment type' })).toBeDisabled()
  })

  it('can be left for the catalogue without saving', async () => {
    const requests = recordRequests()
    const { user, router } = openForm()

    await user.click(await screen.findByRole('link', { name: 'Cancel' }))

    expect(router.state.location.pathname).toBe(ROUTES.EQUIPMENT_CATALOGUE)
    expect(requests.some((request) => request.method === 'POST')).toBe(false)
  })

  it.each(OTHER_STAFF)('sends %s away: only Technical Support add types (AC3)', (_who, account) => {
    const { router } = openFormAs(account)

    expect(router.state.location.pathname).not.toBe(ROUTES.NEW_EQUIPMENT_TYPE)
    expect(screen.queryByLabelText(FIELD.NAME)).not.toBeInTheDocument()
  })
})
