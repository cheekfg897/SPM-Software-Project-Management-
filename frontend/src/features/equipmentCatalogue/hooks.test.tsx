import { screen, waitFor } from '@testing-library/react'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { recordRequests } from '@/test/recordRequests'
import { renderWithProviders } from '@/test/render'

import {
  useCreateEquipmentType,
  useEquipmentType,
  useEquipmentTypes,
  useUpdateEquipmentType,
} from './hooks'

const SESSION = mockSessionFor(MOCK_ACCOUNTS.technicalSupport)
const FOLDING_TABLE = {
  name: 'Folding table',
  description: '',
  total_quantity: 2,
  venue_id: null,
  store_name: 'Jurong store',
}
const MICROPHONE_CHANGES = { ...FOLDING_TABLE, name: 'Microphone', total_quantity: 21 }

function CatalogueProbe() {
  const types = useEquipmentTypes()
  const microphone = useEquipmentType('2')
  const create = useCreateEquipmentType()
  const update = useUpdateEquipmentType()

  return (
    <div>
      <p>Types: {types.data?.map((type) => type.name).join(', ') ?? 'loading'}</p>
      <p>Microphones held: {microphone.data?.total_quantity ?? 'loading'}</p>
      <button onClick={() => create.mutate(FOLDING_TABLE)}>Add a folding table</button>
      <button onClick={() => update.mutate({ equipmentTypeId: '2', changes: MICROPHONE_CHANGES })}>
        Hold more microphones
      </button>
    </div>
  )
}

function TwoTypesProbe() {
  const projector = useEquipmentType('1')
  const microphone = useEquipmentType('2')

  return (
    <p>
      {projector.data?.name ?? 'loading'} and {microphone.data?.name ?? 'loading'}
    </p>
  )
}

async function renderProbe() {
  const rendered = renderWithProviders(<CatalogueProbe />, { session: SESSION })
  await screen.findByText('Microphones held: 12')
  await screen.findByText('Types: Lectern, Microphone, Projector')
  return rendered
}

describe('SCRUM-27 equipment catalogue hooks', () => {
  it('reads each type by its own id, so two never share an answer', async () => {
    renderWithProviders(<TwoTypesProbe />, { session: SESSION })

    expect(await screen.findByText('Projector and Microphone')).toBeInTheDocument()
  })

  it('posts the new type and reads the list again, so it shows there', async () => {
    const requests = recordRequests()
    const { user } = await renderProbe()

    await user.click(screen.getByRole('button', { name: 'Add a folding table' }))

    expect(
      await screen.findByText('Types: Folding table, Lectern, Microphone, Projector'),
    ).toBeInTheDocument()
    const post = requests.find((request) => request.method === 'POST')
    expect(new URL(post?.url ?? '').pathname).toBe('/api/equipment/types')
    expect(await post?.json()).toEqual(FOLDING_TABLE)
  })

  it('patches the type and reads it again, so its new total shows', async () => {
    const requests = recordRequests()
    const { user } = await renderProbe()

    await user.click(screen.getByRole('button', { name: 'Hold more microphones' }))

    expect(await screen.findByText('Microphones held: 21')).toBeInTheDocument()
    await waitFor(() => expect(requests.some((request) => request.method === 'PATCH')).toBe(true))
    const patch = requests.find((request) => request.method === 'PATCH')
    expect(new URL(patch?.url ?? '').pathname).toBe('/api/equipment/types/2')
    expect(await patch?.json()).toEqual(MICROPHONE_CHANGES)
  })
})
