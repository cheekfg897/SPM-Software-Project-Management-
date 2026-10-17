import { screen, waitFor } from '@testing-library/react'
import { http } from 'msw'

import { editEquipmentTypePath, equipmentTypePath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { DUPLICATE_NAME_MESSAGE } from '@/mocks/handlers/equipmentCatalogue'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { bodySent, FIELD, fillIn } from '../test/equipmentTypeForm'

const MICROPHONE_ID = 2
const OTHER_STAFF: [string, MockAccount][] = [
  ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
  ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
  ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
]

function openFormAs(account: MockAccount, equipmentTypeId = MICROPHONE_ID) {
  return renderApp(editEquipmentTypePath(equipmentTypeId), { session: mockSessionFor(account) })
}

function openForm(equipmentTypeId = MICROPHONE_ID) {
  return openFormAs(MOCK_ACCOUNTS.technicalSupport, equipmentTypeId)
}

async function save(user: ReturnType<typeof openForm>['user']) {
  await user.click(screen.getByRole('button', { name: 'Save changes' }))
}

/** What each field holds, by its label. */
async function formValues() {
  await screen.findByLabelText(FIELD.NAME)
  const values: Record<string, string> = {}
  for (const label of Object.values(FIELD)) {
    const field = screen.getByLabelText<HTMLInputElement | HTMLTextAreaElement>(label)
    values[label] = field.value
  }
  return values
}

describe('SCRUM-27 editing an equipment type', () => {
  it('starts from what the type holds now (AC1)', async () => {
    openForm()

    expect(await formValues()).toEqual({
      [FIELD.NAME]: 'Microphone',
      [FIELD.DESCRIPTION]: 'Wireless, handheld.',
      [FIELD.TOTAL]: '12',
      [FIELD.VENUE]: '3',
      [FIELD.STORE]: '',
    })
  })

  it('starts a type kept in a store, with no description, from empty fields for those', async () => {
    openForm(3)

    expect(await formValues()).toMatchObject({
      [FIELD.DESCRIPTION]: '',
      [FIELD.VENUE]: '',
      [FIELD.STORE]: 'Main store',
    })
  })

  it('sends every field and opens the type showing the saved values at once', async () => {
    const requests = recordRequests()
    const { user, router } = openForm()

    await fillIn(user, { [FIELD.TOTAL]: '21', [FIELD.DESCRIPTION]: '' })
    await save(user)

    await screen.findByRole('heading', { level: 1, name: 'Microphone' })
    expect(router.state.location.pathname).toBe(equipmentTypePath(MICROPHONE_ID))
    // Read again before the page opened, so the old total never shows.
    expect(screen.getByText('21')).toBeInTheDocument()
    expect(screen.queryByText('12')).not.toBeInTheDocument()
    expect(screen.getByText('No description')).toBeInTheDocument()
    expect(await bodySent(requests, 'PATCH')).toEqual({
      name: 'Microphone',
      description: '',
      total_quantity: 21,
      venue_id: 3,
      store_name: null,
    })
  })

  it('moves the type from its venue to a store', async () => {
    const requests = recordRequests()
    const { user } = openForm()

    await fillIn(user, { [FIELD.VENUE]: '', [FIELD.STORE]: 'Jurong store' })
    await save(user)

    expect(await screen.findByText('Store: Jurong store')).toBeInTheDocument()
    expect(await bodySent(requests, 'PATCH')).toMatchObject({
      venue_id: null,
      store_name: 'Jurong store',
    })
  })

  it("refuses an emptied total with the backend's message, keeping the type as it was", async () => {
    const { user, router } = openForm()

    await fillIn(user, { [FIELD.TOTAL]: '' })
    await save(user)

    await waitFor(() =>
      expect(screen.getByLabelText(FIELD.TOTAL)).toHaveAccessibleDescription(
        'Field may not be null.',
      ),
    )
    expect(router.state.location.pathname).toBe(editEquipmentTypePath(MICROPHONE_ID))
  })

  it("shows the backend's message for another type's name", async () => {
    const { user } = openForm()

    await fillIn(user, { [FIELD.NAME]: 'Projector' })
    await save(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(DUPLICATE_NAME_MESSAGE)
  })

  it('shows the button as busy while the backend saves', async () => {
    server.use(http.patch('/api/equipment/types/:id', () => new Promise<never>(() => undefined)))
    const { user } = openForm()

    await fillIn(user, { [FIELD.TOTAL]: '21' })
    await save(user)

    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  })

  it('can be left for the type without saving', async () => {
    const { user, router } = openForm()

    await user.click(await screen.findByRole('link', { name: 'Cancel' }))

    expect(router.state.location.pathname).toBe(equipmentTypePath(MICROPHONE_ID))
  })

  it('says what it is loading', () => {
    openForm()

    expect(screen.getByRole('status')).toHaveTextContent('Loading the equipment type')
  })

  it("shows the backend's message instead of a form for a type that does not exist", async () => {
    openForm(999)

    expect(await screen.findByRole('alert')).toHaveTextContent('Equipment type not found.')
    expect(screen.queryByLabelText(FIELD.NAME)).not.toBeInTheDocument()
  })

  it.each(OTHER_STAFF)(
    'sends %s away: only Technical Support change types (AC3)',
    (_who, account) => {
      const { router } = openFormAs(account)

      expect(router.state.location.pathname).not.toBe(editEquipmentTypePath(MICROPHONE_ID))
      expect(screen.queryByLabelText(FIELD.NAME)).not.toBeInTheDocument()
    },
  )
})
