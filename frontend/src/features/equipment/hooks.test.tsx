import { screen, waitFor } from '@testing-library/react'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { MOCK_OPEN_EVENT_REFERENCE } from '@/mocks/handlers/equipmentFixtures'
import { fieldErrorsOf } from '@/lib/api'
import { recordRequests } from '@/test/recordRequests'
import { renderWithProviders } from '@/test/render'

import { useEventAvailability, useEventReservations, useReserveEquipment } from './hooks'

const SESSION = mockSessionFor(MOCK_ACCOUNTS.technicalSupport)
const PROJECTOR_ID = 1

function EquipmentProbe() {
  const availability = useEventAvailability(MOCK_OPEN_EVENT_REFERENCE)
  const reservations = useEventReservations(MOCK_OPEN_EVENT_REFERENCE)
  const reserve = useReserveEquipment(MOCK_OPEN_EVENT_REFERENCE)
  const projector = availability.data?.find((row) => row.equipment_type_id === PROJECTOR_ID)
  const quantityErrors = reserve.error ? fieldErrorsOf(reserve.error).quantity : undefined

  return (
    <div>
      <p>Projector available: {projector?.available ?? 'loading'}</p>
      <p>Reservations: {reservations.data?.length ?? 'loading'}</p>
      <p>Error: {reserve.error?.message ?? 'none'}</p>
      <p>Quantity errors: {quantityErrors?.join(' ') ?? 'none'}</p>
      <button onClick={() => reserve.mutate({ equipment_type_id: PROJECTOR_ID, quantity: 4 })}>
        Reserve four
      </button>
      <button onClick={() => reserve.mutate({ equipment_type_id: PROJECTOR_ID, quantity: 9 })}>
        Reserve nine
      </button>
    </div>
  )
}

describe('SCRUM-45 equipment hooks', () => {
  it('reads availability and reservations from the backend', async () => {
    renderWithProviders(<EquipmentProbe />, { session: SESSION })

    expect(await screen.findByText('Projector available: 6')).toBeInTheDocument()
    expect(await screen.findByText('Reservations: 0')).toBeInTheDocument()
  })
})

describe('SCRUM-46 reserving equipment', () => {
  it('posts the equipment type and quantity to the event', async () => {
    const requests = recordRequests()
    const { user } = renderWithProviders(<EquipmentProbe />, { session: SESSION })
    await screen.findByText('Projector available: 6')

    await user.click(screen.getByRole('button', { name: 'Reserve four' }))

    await waitFor(() => {
      expect(requests.some((request) => request.method === 'POST')).toBe(true)
    })
    const post = requests.find((request) => request.method === 'POST')
    expect(new URL(post?.url ?? '').pathname).toBe(
      `/api/equipment/events/${MOCK_OPEN_EVENT_REFERENCE}/reservations`,
    )
    expect(await post?.json()).toEqual({ equipment_type_id: PROJECTOR_ID, quantity: 4 })
  })

  it('reads availability and reservations again afterwards', async () => {
    const { user } = renderWithProviders(<EquipmentProbe />, { session: SESSION })
    await screen.findByText('Projector available: 6')

    await user.click(screen.getByRole('button', { name: 'Reserve four' }))

    expect(await screen.findByText('Projector available: 2')).toBeInTheDocument()
    expect(await screen.findByText('Reservations: 1')).toBeInTheDocument()
  })

  it("surfaces the backend's refusal, naming how many are available", async () => {
    const { user } = renderWithProviders(<EquipmentProbe />, { session: SESSION })
    await screen.findByText('Projector available: 6')

    await user.click(screen.getByRole('button', { name: 'Reserve nine' }))

    expect(
      await screen.findByText('Quantity errors: Only 6 available for this period.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Error: Invalid request.')).toBeInTheDocument()
    expect(screen.getByText('Projector available: 6')).toBeInTheDocument()
  })
})
