import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { eventEquipmentPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import {
  MOCK_MOVED_EVENT_REFERENCE,
  MOCK_OPEN_EVENT_REFERENCE,
} from '@/mocks/handlers/equipmentFixtures'
import { errorResponse } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-60 on the Equipment page (ADR-0114): what a change left to reassess, with each
 * reservation's period, the event's period now, what is free and any shortfall (AC2), and for
 * Technical Support a Confirm action where the backend says confirming settles it (AC3,
 * ADR-0114 decision 23); otherwise the outcome form above settles it (AC4, AC12). The moved mock
 * event starts with its projectors (fulfilled) and a lectern (reopened, no outcome) marked.
 */

const TECHNICAL_SUPPORT = mockSessionFor(MOCK_ACCOUNTS.technicalSupport)
const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
const MOVED_PAGE = eventEquipmentPath(MOCK_MOVED_EVENT_REFERENCE)
const REASSESSMENTS_PATH = `/api/equipment/events/${MOCK_MOVED_EVENT_REFERENCE}/reassessments`
const LIST_NAME = 'Reservations to reassess'
const RECORD_THE_OUTCOME =
  "This equipment's request has no current outcome. Record its outcome instead: that settles the reservation."
const OUTCOME_HINT = (name: string) =>
  `Record the outcome for ${name} above; that settles the reservation.`

type User = ReturnType<typeof renderApp>['user']

async function reassessmentList(): Promise<HTMLElement> {
  return screen.findByRole('list', { name: LIST_NAME })
}

/** The list item about one equipment type. */
async function itemFor(name: string): Promise<HTMLElement> {
  const items = within(await reassessmentList()).getAllByRole('listitem')
  const item = items.find((candidate) => candidate.textContent?.startsWith(name))
  if (item === undefined) {
    throw new Error(`No reservation to reassess for ${name}.`)
  }
  return item
}

/** One type's reassessment as the backend sends it: three projectors, `changes` on top. */
function projectorReassessment(changes: Record<string, unknown>) {
  return {
    equipment_type_id: 1,
    equipment_type_name: 'Projector',
    reservations: [
      {
        id: 901,
        equipment_type_id: 1,
        equipment_type_name: 'Projector',
        quantity: 3,
        starts_at: '2026-10-09T19:30:00+08:00',
        ends_at: '2026-10-09T22:00:00+08:00',
        reserved_by: 'Tariq Hassan',
        created_at: '2026-10-02T09:00:00+08:00',
        needs_attention: false,
        preparation_status: 'in_progress',
        preparation_notes: 'Bulbs checked.',
      },
    ],
    reserved_quantity: 3,
    starts_at: '2026-10-12T19:30:00+08:00',
    ends_at: '2026-10-12T22:00:00+08:00',
    available: 6,
    shortfall: 0,
    confirmable: true,
    ...changes,
  }
}

function confirmButtonFor(name: string) {
  return screen.getByRole('button', { name: `Confirm ${name} for the event's period now` })
}

async function confirmAsTechnicalSupport(name: string): Promise<User> {
  const { user } = renderApp(MOVED_PAGE, { session: TECHNICAL_SUPPORT })
  await itemFor(name)
  await user.click(confirmButtonFor(name))
  return user
}

describe('SCRUM-60 Equipment page: reservations to reassess', () => {
  it('shows the loading text until the equipment, reassessments included, is read', async () => {
    renderApp(MOVED_PAGE, { session: TECHNICAL_SUPPORT })

    expect(screen.getByText('Loading equipment…')).toBeInTheDocument()
    await reassessmentList()
    expect(screen.queryByText('Loading equipment…')).not.toBeInTheDocument()
  })

  it("shows each type's reserved units, the period they hold, the period now and what is free (AC2)", async () => {
    renderApp(MOVED_PAGE, { session: TECHNICAL_SUPPORT })

    const projector = await itemFor('Projector')
    expect(projector).toHaveTextContent('Projector: 3 reserved')
    expect(projector).toHaveTextContent('Held for 9 Oct, 7:30 pm – 10:00 pm')
    expect(projector).toHaveTextContent("The event's period now: 12 Oct, 7:30 pm – 10:00 pm")
    expect(projector).toHaveTextContent('6 free for it, enough for every reserved unit.')
    expect(await itemFor('Lectern')).toHaveTextContent('Lectern: 1 reserved')
  })

  it('shows a shortfall, and points to the outcome form instead of confirming (AC4)', async () => {
    server.use(
      http.get(REASSESSMENTS_PATH, () =>
        HttpResponse.json([
          projectorReassessment({ available: 1, shortfall: 2, confirmable: false }),
        ]),
      ),
    )
    renderApp(MOVED_PAGE, { session: TECHNICAL_SUPPORT })

    const projector = await itemFor('Projector')
    expect(projector).toHaveTextContent('1 free for it: 2 short.')
    expect(projector).toHaveTextContent(OUTCOME_HINT('Projector'))
    expect(within(projector).queryByRole('button', { name: /Confirm/ })).not.toBeInTheDocument()
  })

  it('points a line with no current outcome to the outcome form, with nothing short (AC12)', async () => {
    renderApp(MOVED_PAGE, { session: TECHNICAL_SUPPORT })

    const lectern = await itemFor('Lectern')
    expect(lectern).toHaveTextContent('2 free for it, enough for every reserved unit.')
    expect(lectern).toHaveTextContent(OUTCOME_HINT('Lectern'))
    expect(within(lectern).queryByRole('button', { name: /Confirm/ })).not.toBeInTheDocument()
  })

  it('offers Confirm when the backend says so though short, saying what it keeps', async () => {
    server.use(
      http.get(REASSESSMENTS_PATH, () =>
        HttpResponse.json([projectorReassessment({ available: 1, shortfall: 2 })]),
      ),
    )
    renderApp(MOVED_PAGE, { session: TECHNICAL_SUPPORT })

    const projector = await itemFor('Projector')
    expect(projector).toHaveTextContent('Confirming keeps the 1 free and releases the rest.')
    expect(projector).not.toHaveTextContent(OUTCOME_HINT('Projector'))
    expect(confirmButtonFor('Projector')).toBeInTheDocument()
  })

  it('names a period two reservations share once', async () => {
    const [reservation] = projectorReassessment({}).reservations
    server.use(
      http.get(REASSESSMENTS_PATH, () =>
        HttpResponse.json([
          projectorReassessment({ reservations: [reservation, { ...reservation, id: 905 }] }),
        ]),
      ),
    )
    renderApp(MOVED_PAGE, { session: TECHNICAL_SUPPORT })

    const projector = await itemFor('Projector')
    expect(within(projector).getByText(/^Held for/)).toHaveTextContent(
      /^Held for 9 Oct, 7:30 pm – 10:00 pm$/,
    )
  })

  it('shows nothing to reassess on an event with nothing marked', async () => {
    renderApp(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE), { session: TECHNICAL_SUPPORT })

    await screen.findByRole('heading', { name: 'What this event needs' })
    expect(screen.queryByRole('heading', { name: LIST_NAME })).not.toBeInTheDocument()
  })

  it('shows the coordinator the same, with nothing to confirm', async () => {
    renderApp(MOVED_PAGE, { session: COORDINATOR })

    expect(await itemFor('Projector')).toHaveTextContent('Projector: 3 reserved')
    expect(screen.queryByRole('button', { name: /Confirm/ })).not.toBeInTheDocument()
  })

  it("shows the backend's message when the reassessments can't be read", async () => {
    server.use(
      http.get(REASSESSMENTS_PATH, () =>
        errorResponse(
          409,
          'event_period_incomplete',
          'The event has no complete date and times yet.',
        ),
      ),
    )
    renderApp(MOVED_PAGE, { session: TECHNICAL_SUPPORT })

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The event has no complete date and times yet.',
    )
  })
})

describe('SCRUM-60 Equipment page: confirming a reservation (AC3)', () => {
  it('confirms the type and reads the equipment again, so it leaves the list', async () => {
    const requests = recordRequests()
    await confirmAsTechnicalSupport('Projector')

    await waitFor(() => {
      expect(
        within(screen.getByRole('list', { name: LIST_NAME })).getAllByRole('listitem'),
      ).toHaveLength(1)
    })
    const posted = requests.filter((request) => request.method === 'POST')
    expect(posted.map((request) => new URL(request.url).pathname)).toEqual([
      `${REASSESSMENTS_PATH}/1/confirm`,
    ])
    const reserved = screen.getByRole('table', { name: 'Reserved equipment' })
    expect(
      within(reserved).getByRole('cell', { name: '12 Oct, 7:30 pm – 10:00 pm' }),
    ).toBeInTheDocument()
  })

  it("shows the backend's refusal in its own words, and reads the equipment again", async () => {
    server.use(
      http.post(`${REASSESSMENTS_PATH}/1/confirm`, () =>
        errorResponse(409, 'conflict', RECORD_THE_OUTCOME),
      ),
    )
    const requests = recordRequests()
    await confirmAsTechnicalSupport('Projector')

    expect(await screen.findByRole('alert')).toHaveTextContent(RECORD_THE_OUTCOME)
    await waitFor(() => {
      const reads = requests.filter(
        (request) =>
          request.method === 'GET' && new URL(request.url).pathname === REASSESSMENTS_PATH,
      )
      expect(reads).toHaveLength(2)
    })
    expect(await itemFor('Projector')).toHaveTextContent('Projector: 3 reserved')
  })

  it('shows a shortfall refusal the backend sends after the list was read', async () => {
    const message =
      "Projector: only 2 free for the event's period, not the 3 to keep. Record an outcome that provides no more than 2."
    server.use(
      http.post(`${REASSESSMENTS_PATH}/1/confirm`, () =>
        errorResponse(409, 'reservation_cannot_move', message),
      ),
    )
    await confirmAsTechnicalSupport('Projector')

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
  })
})
