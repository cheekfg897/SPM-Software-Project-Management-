import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import { eventEquipmentPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import {
  MOCK_OPEN_EVENT_REFERENCE,
  mockStatusEventReference,
} from '@/mocks/handlers/equipmentFixtures'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import type { EquipmentReservation } from '../api'
import { reserveProjectors } from '../test/reserveProjectors'

/** The mock coordinator's event in Safety Review: the Safety Officer hasn't approved it yet. */
const AWAITING_SAFETY_EVENT_REFERENCE = mockStatusEventReference(EVENT_REQUEST_STATUS.SAFETY_REVIEW)
const SAFETY_APPROVAL_MESSAGE =
  "Preparation details can't be recorded until the Safety Officer has approved the event's" +
  ' Operational Safety Check.'

/** A reservation as the backend sends it, already under way with a note. */
const RESERVATION_IN_PROGRESS: EquipmentReservation = {
  id: 1,
  equipment_type_id: 1,
  equipment_type_name: 'Projector',
  quantity: 2,
  starts_at: '2026-10-12T19:30:00+08:00',
  ends_at: '2026-10-12T22:00:00+08:00',
  reserved_by: 'Tariq Hassan',
  created_at: '2026-10-10T09:00:00+08:00',
  needs_attention: false,
  preparation_status: 'in_progress',
  preparation_notes: 'Lamps tested.',
}

/** As Technical Support, open the event's Equipment page and reserve one projector. */
async function reserveAsTechnicalSupport(reference: string) {
  const view = renderApp(eventEquipmentPath(reference), {
    session: mockSessionFor(MOCK_ACCOUNTS.technicalSupport),
  })
  await reserveProjectors(view.user, '1')
  await screen.findByRole('table', { name: 'Reserved equipment' })
  return view
}

/** The reserved equipment table's row for the projectors. */
function projectorRow() {
  const table = screen.getByRole('table', { name: 'Reserved equipment' })
  const row = within(table).getByRole('cell', { name: 'Projector' }).closest('tr')
  if (row === null) {
    throw new Error('The reserved equipment table has no Projector row.')
  }
  return within(row)
}

/** The PUT the page sent, read as JSON. */
async function sentPreparation(requests: Request[]) {
  const update = requests.find((sent) => sent.method === 'PUT')
  const body: unknown = await update?.json()
  return { url: update?.url, body }
}

describe("SCRUM-85 Technical Support record a reservation's preparation", () => {
  it('shows each reservation as not started, with no notes, until something is recorded', async () => {
    await reserveAsTechnicalSupport(MOCK_OPEN_EVENT_REFERENCE)

    const row = projectorRow()
    expect(row.getByRole('cell', { name: 'Not started' })).toBeInTheDocument()
    expect(row.getByRole('cell', { name: 'None' })).toBeInTheDocument()
    expect(row.getByLabelText('Preparation status for Projector')).toHaveValue('not_started')
  })

  it('sends the status and notes, then shows what the backend saved (AC1)', async () => {
    const requests = recordRequests()
    const { user } = await reserveAsTechnicalSupport(MOCK_OPEN_EVENT_REFERENCE)

    await user.selectOptions(projectorRow().getByLabelText(/^Preparation status/), 'Ready')
    await user.type(projectorRow().getByLabelText(/^Preparation notes/), 'Lamps tested.')
    await user.click(screen.getByRole('button', { name: 'Save preparation for Projector' }))

    await waitFor(() => expect(projectorRow().getByRole('cell', { name: 'Ready' })).toBeVisible())
    expect(projectorRow().getByRole('cell', { name: 'Lamps tested.' })).toBeInTheDocument()
    expect(projectorRow().getByRole('status')).toHaveTextContent('Preparation saved.')
    const sent = await sentPreparation(requests)
    expect(sent.url).toContain('/api/equipment/reservations/1/preparation')
    expect(sent.body).toEqual({ status: 'ready', notes: 'Lamps tested.' })
  })

  it('leaves empty notes out, which clears them', async () => {
    const requests = recordRequests()
    const { user } = await reserveAsTechnicalSupport(MOCK_OPEN_EVENT_REFERENCE)

    await user.selectOptions(projectorRow().getByLabelText(/^Preparation status/), 'In progress')
    await user.click(screen.getByRole('button', { name: 'Save preparation for Projector' }))

    await waitFor(() =>
      expect(projectorRow().getByRole('cell', { name: 'In progress' })).toBeVisible(),
    )
    expect((await sentPreparation(requests)).body).toEqual({ status: 'in_progress' })
  })

  it("shows the backend's refusal before the Safety Officer has approved the event (AC5)", async () => {
    const { user } = await reserveAsTechnicalSupport(AWAITING_SAFETY_EVENT_REFERENCE)

    await user.selectOptions(projectorRow().getByLabelText(/^Preparation status/), 'Ready')
    await user.click(screen.getByRole('button', { name: 'Save preparation for Projector' }))

    expect(await projectorRow().findByRole('alert')).toHaveTextContent(SAFETY_APPROVAL_MESSAGE)
    expect(projectorRow().getByRole('cell', { name: 'Not started' })).toBeInTheDocument()
  })

  it("shows the backend's message under the notes it refuses", async () => {
    const { user } = await reserveAsTechnicalSupport(MOCK_OPEN_EVENT_REFERENCE)

    await user.type(projectorRow().getByLabelText(/^Preparation notes/), '   ')
    await user.click(screen.getByRole('button', { name: 'Save preparation for Projector' }))

    expect(await projectorRow().findByText('Must not be blank.')).toBeInTheDocument()
    expect(projectorRow().queryByRole('alert')).toBeNull()
  })
})

describe("SCRUM-85 the coordinator sees each reservation's preparation", () => {
  it('shows the status and notes, with no way to record them (AC2)', async () => {
    server.use(
      http.get(`/api/equipment/events/${MOCK_OPEN_EVENT_REFERENCE}/reservations`, () =>
        HttpResponse.json([RESERVATION_IN_PROGRESS]),
      ),
    )
    renderApp(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE), {
      session: mockSessionFor(MOCK_ACCOUNTS.coordinator),
    })
    const table = await screen.findByRole('table', { name: 'Reserved equipment' })

    const headers = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent)
    expect(headers).toEqual([
      'Equipment',
      'Quantity',
      'Reserved by',
      'When',
      'Preparation',
      'Preparation notes',
    ])
    expect(projectorRow().getByRole('cell', { name: 'In progress' })).toBeInTheDocument()
    expect(projectorRow().getByRole('cell', { name: 'Lamps tested.' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Save preparation/ })).toBeNull()
  })
})
