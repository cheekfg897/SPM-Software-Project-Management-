import { act, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { MOCK_OPEN_EVENT_REFERENCE } from '@/mocks/handlers/equipmentFixtures'
import { fieldErrorsOf } from '@/lib/api'
import { server } from '@/mocks/server'
import { signedIn } from '@/store'
import { recordRequests } from '@/test/recordRequests'
import { renderHookWithProviders, renderWithProviders } from '@/test/render'

import {
  useAddEquipmentLine,
  useEventAvailability,
  useEventEquipmentLines,
  useEventReservations,
  useRemoveEquipmentLine,
  useReserveEquipment,
  useUpdateEquipmentLine,
} from './hooks'

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

  it('reads availability again after a refusal, so the table shows what the backend has now', async () => {
    const { user } = renderWithProviders(<EquipmentProbe />, { session: SESSION })
    await screen.findByText('Projector available: 6')
    // Meanwhile someone else reserved five more, so the backend now has one free.
    server.use(
      http.get(`/api/equipment/events/${MOCK_OPEN_EVENT_REFERENCE}/availability`, () =>
        HttpResponse.json([
          {
            equipment_type_id: PROJECTOR_ID,
            equipment_type_name: 'Projector',
            available: 1,
            requested: 8,
            shortfall: 7,
          },
        ]),
      ),
    )

    await user.click(screen.getByRole('button', { name: 'Reserve nine' }))

    expect(await screen.findByText('Projector available: 1')).toBeInTheDocument()
  })
})

describe('SCRUM-37 equipment line hooks', () => {
  const LINES_PATH = `/api/events/requests/${MOCK_OPEN_EVENT_REFERENCE}/equipment`
  const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)

  function linesReads(requests: Request[]): number {
    const reads = requests.filter(
      (request) => request.method === 'GET' && new URL(request.url).pathname === LINES_PATH,
    )
    return reads.length
  }

  function useLineHooks() {
    return {
      lines: useEventEquipmentLines(MOCK_OPEN_EVENT_REFERENCE),
      add: useAddEquipmentLine(MOCK_OPEN_EVENT_REFERENCE),
      update: useUpdateEquipmentLine(MOCK_OPEN_EVENT_REFERENCE),
      remove: useRemoveEquipmentLine(MOCK_OPEN_EVENT_REFERENCE),
    }
  }

  it('reads the lines again when someone else signs in, since the answer depends on who asks', async () => {
    const requests = recordRequests()
    const { result, store } = renderHookWithProviders(useLineHooks, { session: SESSION })
    await waitFor(() => expect(result.current.lines.data?.equipment_lines).toHaveLength(2))

    act(() => {
      store.dispatch(signedIn(COORDINATOR))
    })

    await waitFor(() => expect(linesReads(requests)).toBe(2))
  })

  type LineHooks = ReturnType<typeof useLineHooks>

  // A second Projector line is a conflict, the microphones can't go below the four that will be
  // provided, and there is no line 999.
  it.each([
    ['add', (hooks: LineHooks) => hooks.add.mutate({ equipment_type_id: 1, quantity: 1 })],
    ['update', (hooks: LineHooks) => hooks.update.mutate({ lineId: 42, body: { quantity: 3 } })],
    ['remove', (hooks: LineHooks) => hooks.remove.mutate(999)],
  ] as const)(
    'reads the lines again after a refused %s, to show what the backend has now',
    async (name, send) => {
      const { result } = renderHookWithProviders(useLineHooks, { session: COORDINATOR })
      await waitFor(() => expect(result.current.lines.data?.equipment_lines).toHaveLength(2))
      // Meanwhile someone else removed every line.
      server.use(
        http.get(LINES_PATH, () =>
          HttpResponse.json({ event: { name: 'Annual Partner Summit' }, equipment_lines: [] }),
        ),
      )

      act(() => {
        send(result.current)
      })

      await waitFor(() => expect(result.current[name].isError).toBe(true))
      await waitFor(() => expect(result.current.lines.data?.equipment_lines).toEqual([]))
    },
  )
})
