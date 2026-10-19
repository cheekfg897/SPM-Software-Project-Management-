import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { equipmentTypePath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { definitionsIn } from '../test/definitions'
import { OTHER_STAFF } from '../test/staff'

/** Ten projectors are held. */
const PROJECTOR_ID = 1
/** Two lecterns are held. */
const LECTERN_ID = 3
const MISSING = 'Missing data for required field.'

function openTypeAs(account: MockAccount, equipmentTypeId: number) {
  return renderApp(equipmentTypePath(equipmentTypeId), { session: mockSessionFor(account) })
}

function openAsTechnicalSupport(equipmentTypeId = PROJECTOR_ID) {
  return openTypeAs(MOCK_ACCOUNTS.technicalSupport, equipmentTypeId)
}

async function section() {
  return screen.findByRole('region', { name: 'Out of service' })
}

/** The section's counts, each label with its value. */
async function counts() {
  return definitionsIn(await screen.findByRole('group', { name: 'Units in and out of service' }))
}

type User = ReturnType<typeof renderApp>['user']

/** Fill in the form, leaving a blank value out, and send it. */
async function takeOut(user: User, quantity: string, reason: string) {
  const form = await screen.findByRole('form', { name: 'Take units out of service' })
  if (quantity !== '') {
    await user.type(within(form).getByLabelText('Quantity'), quantity)
  }
  if (reason !== '') {
    await user.selectOptions(within(form).getByLabelText('Reason'), reason)
  }
  await user.click(within(form).getByRole('button', { name: 'Take out of service' }))
  return form
}

describe('SCRUM-47 units out of service on an equipment type page', () => {
  it('shows Technical Support every unit in service while none are out (AC2)', async () => {
    openAsTechnicalSupport()

    expect(await counts()).toEqual({
      'In service': '10 of 10',
      Damaged: '0',
      'Under maintenance': '0',
    })
    expect(within(await section()).getByText('Every unit is in service.')).toBeInTheDocument()
  })

  it('takes units out as Damaged, showing the new counts and who recorded it when (AC1, AC4)', async () => {
    const requests = recordRequests()
    const { user } = openAsTechnicalSupport()

    const form = await takeOut(user, '2', 'Damaged')

    const table = await screen.findByRole('table', { name: 'Units out of service' })
    const cells = within(table)
      .getAllByRole('cell')
      .map((cell) => cell.textContent)
    expect(cells.slice(0, 3)).toEqual(['2', 'Damaged', 'Recorded by Tariq Hassan, 7 Oct, 2:05 pm'])
    await waitFor(async () =>
      expect(await counts()).toEqual({
        'In service': '8 of 10',
        Damaged: '2',
        'Under maintenance': '0',
      }),
    )
    const posted = requests.find((request) => request.method === 'POST')
    expect(await posted?.json()).toEqual({ quantity: 2, reason: 'damaged' })
    expect(within(form).getByLabelText('Quantity')).toHaveValue(null)
    expect(within(form).getByLabelText('Reason')).toHaveValue('')
  })

  it('counts units under maintenance apart from damaged ones', async () => {
    const { user } = openAsTechnicalSupport()

    await takeOut(user, '1', 'Damaged')
    await screen.findByRole('table', { name: 'Units out of service' })
    await takeOut(user, '3', 'Under maintenance')

    await waitFor(async () =>
      expect(await counts()).toEqual({
        'In service': '6 of 10',
        Damaged: '1',
        'Under maintenance': '3',
      }),
    )
  })

  it("leaves blank fields out, so the backend's messages show under each", async () => {
    const requests = recordRequests()
    const { user } = openAsTechnicalSupport()

    const form = await takeOut(user, '', '')

    expect(await within(form).findAllByText(MISSING)).toHaveLength(2)
    const posted = requests.find((request) => request.method === 'POST')
    expect(await posted?.json()).toEqual({})
    expect(within(form).queryByRole('alert')).not.toBeInTheDocument()
  })

  it("shows the backend's refusal of more units than are in service under the quantity", async () => {
    const { user } = openAsTechnicalSupport(LECTERN_ID)

    const form = await takeOut(user, '3', 'Under maintenance')

    const quantity = within(form).getByLabelText('Quantity')
    await waitFor(() =>
      expect(quantity).toHaveAccessibleDescription('Only 2 units are in service.'),
    )
    expect(within(form).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('puts units back in service, saying who did it when, and counts them again (AC1, AC4)', async () => {
    const { user } = openAsTechnicalSupport()
    await takeOut(user, '2', 'Damaged')

    await user.click(
      await screen.findByRole('button', { name: 'Put 2 Damaged units back in service' }),
    )

    expect(await screen.findByRole('status')).toHaveTextContent(
      '2 Damaged units are back in service. Put back by Tariq Hassan, 8 Oct, 9:30 am.',
    )
    expect(await screen.findByText('Every unit is in service.')).toBeInTheDocument()
    expect(await counts()).toMatchObject({ 'In service': '10 of 10', Damaged: '0' })
  })

  it('names a single unit in the singular', async () => {
    const { user } = openAsTechnicalSupport()
    await takeOut(user, '1', 'Under maintenance')

    await user.click(
      await screen.findByRole('button', { name: 'Put 1 Under maintenance unit back in service' }),
    )

    expect(await screen.findByRole('status')).toHaveTextContent(
      '1 Under maintenance unit is back in service.',
    )
  })

  it("shows the backend's message when putting units back is refused", async () => {
    server.use(
      http.post('/api/equipment/out-of-service/:entryId/return', () =>
        HttpResponse.json(
          { error: 'conflict', message: 'These units are already back in service.' },
          { status: 409 },
        ),
      ),
    )
    const { user } = openAsTechnicalSupport()
    await takeOut(user, '2', 'Damaged')

    await user.click(
      await screen.findByRole('button', { name: 'Put 2 Damaged units back in service' }),
    )

    expect(await within(await section()).findByRole('alert')).toHaveTextContent(
      'These units are already back in service.',
    )
  })

  it('says what it is loading, then the backend message if the list cannot be read', async () => {
    server.use(
      http.get('/api/equipment/types/:equipmentTypeId/out-of-service', () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'Out-of-service units are unavailable.' },
          { status: 500 },
        ),
      ),
    )
    openAsTechnicalSupport()

    expect(await screen.findByText('Loading units out of service…')).toBeInTheDocument()
    expect(await within(await section()).findByRole('alert')).toHaveTextContent(
      'Out-of-service units are unavailable.',
    )
  })

  it.each(OTHER_STAFF)(
    'shows %s no out-of-service section, and asks the backend for none',
    async (_who, account) => {
      const requests = recordRequests()
      openTypeAs(account, PROJECTOR_ID)

      await screen.findByText('Total quantity held')
      expect(screen.queryByRole('region', { name: 'Out of service' })).not.toBeInTheDocument()
      expect(requests.some((request) => request.url.includes('out-of-service'))).toBe(false)
    },
  )
})
