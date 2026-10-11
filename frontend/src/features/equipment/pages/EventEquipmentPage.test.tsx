import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { eventEquipmentPath, ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import {
  MOCK_CLOSED_EVENT_REFERENCE,
  MOCK_OPEN_EVENT_REFERENCE,
} from '@/mocks/handlers/equipmentFixtures'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

const TECHNICAL_SUPPORT = mockSessionFor(MOCK_ACCOUNTS.technicalSupport)
const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
const OPEN_PAGE = eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE)

/** The Projector row's cell texts: name, available, requested, shortfall. */
function projectorCells(): (string | null)[] {
  const table = screen.getByRole('table', { name: 'Equipment availability' })
  const row = within(table).getByRole('cell', { name: 'Projector' }).closest('tr')
  return [...(row?.querySelectorAll('td') ?? [])].slice(0, 4).map((cell) => cell.textContent)
}

async function reserveProjectors(
  user: ReturnType<typeof renderApp>['user'],
  quantity: string,
): Promise<void> {
  await user.type(await screen.findByLabelText('Quantity of Projector'), quantity)
  await user.click(screen.getByRole('button', { name: 'Reserve Projector' }))
}

describe('SCRUM-45 equipment page: what is free for the event', () => {
  it('shows each type with available, requested and the shortfall in words', async () => {
    renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: `Equipment for ${MOCK_OPEN_EVENT_REFERENCE}`,
      }),
    ).toBeInTheDocument()
    const table = await screen.findByRole('table', { name: 'Equipment availability' })
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent)
    expect(headers).toEqual(['Equipment', 'Available', 'Requested', 'Shortfall', 'Reserve'])
    await screen.findByRole('table', { name: 'Equipment availability' })
    expect(projectorCells()).toEqual(['Projector', '6', '8', 'Short by 2'])
    const microphone = within(table).getByRole('cell', { name: 'Microphone' }).closest('tr')
    expect(microphone).toHaveTextContent('None')
  })

  it('says it is loading, then shows the backend message when the event is not found', async () => {
    renderApp(eventEquipmentPath('EVR-NOPE'), { session: TECHNICAL_SUPPORT })

    expect(screen.getByText('Loading equipment…')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('Event request not found.')
  })

  it('shows the backend message when only the reservations cannot be read', async () => {
    server.use(
      http.get(`/api/equipment/events/${MOCK_OPEN_EVENT_REFERENCE}/reservations`, () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'Reservations are unavailable.' },
          { status: 500 },
        ),
      ),
    )
    renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    expect(await screen.findByRole('alert')).toHaveTextContent('Reservations are unavailable.')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('says when nothing has been reserved yet', async () => {
    renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    expect(
      await screen.findByText('No equipment has been reserved for this event yet.'),
    ).toBeInTheDocument()
  })

  it('names a reserver whose account is gone as unknown', async () => {
    server.use(
      http.get(`/api/equipment/events/${MOCK_OPEN_EVENT_REFERENCE}/reservations`, () =>
        HttpResponse.json([
          {
            id: 1,
            equipment_type_id: 1,
            equipment_type_name: 'Projector',
            quantity: 2,
            starts_at: '2026-10-12T19:30:00+08:00',
            ends_at: '2026-10-12T22:00:00+08:00',
            reserved_by: null,
            created_at: '2026-10-10T09:00:00+08:00',
          },
        ]),
      ),
    )
    renderApp(OPEN_PAGE, { session: COORDINATOR })

    const table = await screen.findByRole('table', { name: 'Reserved equipment' })
    expect(within(table).getByText('Unknown')).toBeInTheDocument()
    expect(within(table).getByText(/12 Oct/)).toBeInTheDocument()
  })
})

describe('SCRUM-46 equipment page: reserving', () => {
  it('sends the quantity, clears the field and shows the reduced numbers and the reservation', async () => {
    const requests = recordRequests()
    const { user } = renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    await reserveProjectors(user, '4')

    const posted = requests.find((request) => request.method === 'POST')
    expect(await posted?.json()).toEqual({ equipment_type_id: 1, quantity: 4 })
    await waitFor(() => expect(projectorCells()).toEqual(['Projector', '2', '8', 'Short by 6']))
    const reserved = within(screen.getByRole('table', { name: 'Reserved equipment' }))
    expect(reserved.getByText('Tariq Hassan')).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity of Projector')).toHaveValue(null)
  })

  it('shows the backend message naming how many are available when asking for too many', async () => {
    const { user } = renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    await reserveProjectors(user, '7')

    expect(await screen.findByText('Only 6 available for this period.')).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity of Projector')).toBeInvalid()
    expect(screen.getByLabelText('Quantity of Projector')).toHaveValue(7)
  })

  it('shows a refusal that is not about a field as an alert', async () => {
    const { user } = renderApp(eventEquipmentPath(MOCK_CLOSED_EVENT_REFERENCE), {
      session: TECHNICAL_SUPPORT,
    })

    await reserveProjectors(user, '1')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Equipment can't be reserved for an event that is completed, cancelled or rejected.",
    )
  })

  it('shows a coordinator the same tables with no way to reserve', async () => {
    renderApp(OPEN_PAGE, { session: COORDINATOR })

    const table = await screen.findByRole('table', { name: 'Equipment availability' })
    expect(within(table).getByRole('cell', { name: 'Projector' })).toBeInTheDocument()
    expect(within(table).queryByRole('columnheader', { name: 'Reserve' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Quantity of/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Reserve/ })).not.toBeInTheDocument()
  })
})

describe('SCRUM-45 equipment page: who may open it', () => {
  it('sends a visitor to staff log in, to come back here afterwards', () => {
    const { router } = renderApp(OPEN_PAGE)

    expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN)
    expect(router.state.location.search).toContain(encodeURIComponent(OPEN_PAGE))
  })

  it('sends an attendee to their own home', () => {
    const { router } = renderApp(OPEN_PAGE, { session: mockSessionFor(MOCK_ACCOUNTS.attendee) })

    expect(router.state.location.pathname).toBe(ROUTES.EVENTS)
  })
})
