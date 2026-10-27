import { screen, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import type { EquipmentAwaitingAction } from '../api'

/**
 * SCRUM-38: Technical Support's Staff home lists the equipment still awaiting them, soonest event
 * first as the backend sends it, each event opening its Equipment page (ADR-0022, ADR-0061).
 * Unless a test says otherwise, the rows come from the mock in src/mocks/handlers/techSupport.ts.
 */

const QUEUE_NAME = 'Equipment awaiting action'
const AWAITING_PATH = '/api/events/requests/awaiting-equipment'
const TYPES_PATH = '/api/equipment/types'

function openStaffHome(account: MockAccount) {
  return renderApp(ROUTES.STAFF_HOME, { session: mockSessionFor(account) })
}

async function queue(): Promise<HTMLElement> {
  return screen.findByRole('list', { name: QUEUE_NAME })
}

/** One queued event on 20 November, asking for 3 of equipment type `typeId`. */
function queued(name: string, daysRemaining: number, typeId = 1): EquipmentAwaitingAction {
  return {
    event: {
      reference: `EVR-Q${daysRemaining}`,
      name,
      proposed_date: '2026-11-20',
      end_date: '2026-11-20',
      start_time: '10:00:00',
      end_time: '12:00:00',
    },
    equipment_lines: [
      {
        id: 900 + daysRemaining,
        equipment_type_id: typeId,
        quantity: 3,
        notes: null,
        status: 'requested',
      },
    ],
    days_remaining: daysRemaining,
    equipment_type_ids_to_reassess: [],
  }
}

/** The backend answers the queue with exactly these rows. */
function answerQueueWith(rows: EquipmentAwaitingAction[]) {
  server.use(http.get(AWAITING_PATH, () => HttpResponse.json({ equipment_requests: rows })))
}

/** The backend refuses `path` with a message only it could have sent. */
function failWith(path: string, message: string) {
  server.use(
    http.get(path, () => HttpResponse.json({ error: 'internal_error', message }, { status: 500 })),
  )
}

describe('SCRUM-38 Staff home: the equipment awaiting action, for Technical Support', () => {
  it('lists the events in the order the backend sends them (AC3)', async () => {
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    const headings = within(await queue()).getAllByRole('heading')
    expect(headings.map((heading) => heading.textContent)).toEqual([
      'Sunrise Wellness Walk',
      'Evening Product Showcase',
      'Leadership Offsite',
      'Data Science Meetup',
      'Charity Fun Run',
      'Board Breakfast Briefing',
      'Harbourfront Careers Fair',
      'Year-End Town Hall',
    ])
  })

  it('keeps an order the browser would sort differently', async () => {
    answerQueueWith([queued('Later Launch', 12), queued('Sooner Showcase', 3)])
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    const headings = within(await queue()).getAllByRole('heading')
    expect(headings.map((heading) => heading.textContent)).toEqual([
      'Later Launch',
      'Sooner Showcase',
    ])
  })

  it("shows each event's date and time, and its equipment types and quantities by name (AC2)", async () => {
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    const showcase = within(await queue()).getAllByRole('listitem')[1]
    expect(showcase).toHaveTextContent('Mon, 12 Oct · 7:30 pm – 10:00 pm')
    expect(showcase).toHaveTextContent('EVR-MOCK0001 · Projector × 2, Microphone × 4')
    expect(showcase).toHaveTextContent('7 days left')
  })

  it('marks each line whose reservation a change left to reassess (SCRUM-60 AC6)', async () => {
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    const offsite = within(await queue()).getAllByRole('listitem')[2]
    expect(offsite).toHaveTextContent(
      'EVR-MOCK0004 · Projector × 3 (reservation to reassess), Lectern × 2 (reservation to reassess)',
    )
    const showcase = within(await queue()).getAllByRole('listitem')[1]
    expect(showcase).not.toHaveTextContent('reassess')
  })

  it.each([
    [0, 'Today'],
    [1, '1 day left'],
    [2, '2 days left'],
  ])('reads %i days remaining as "%s" (AC2)', async (days, label) => {
    answerQueueWith([queued('Rooftop Social', days)])
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    expect(within(await queue()).getByRole('listitem')).toHaveTextContent(label)
  })

  it('names a type the catalogue does not list by its id, rather than hiding the line', async () => {
    answerQueueWith([queued('Rooftop Social', 4, 77)])
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    expect(within(await queue()).getByRole('listitem')).toHaveTextContent('Equipment type 77 × 3')
  })

  it("opens each event's Equipment page", async () => {
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    const link = within(await queue()).getByRole('link', { name: /Evening Product Showcase/ })
    expect(link).toHaveAttribute('href', '/events/EVR-MOCK0001/equipment')
  })

  it('says so when nothing is awaiting action', async () => {
    answerQueueWith([])
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    expect(
      await screen.findByText('No equipment requests are awaiting action.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: QUEUE_NAME })).not.toBeInTheDocument()
  })

  it.each([
    ['the queue', AWAITING_PATH],
    ['the equipment types', TYPES_PATH],
  ])("shows the backend's message when %s can't be read", async (_what, path) => {
    failWith(path, `Could not read ${path} just now.`)
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    expect(await screen.findByText(`Could not read ${path} just now.`)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: QUEUE_NAME })).not.toBeInTheDocument()
  })

  it("shows the queue's message when both can't be read", async () => {
    failWith(AWAITING_PATH, 'The queue is down.')
    failWith(TYPES_PATH, 'The catalogue is down.')
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    expect(await screen.findByText('The queue is down.')).toBeInTheDocument()
    expect(screen.queryByText('The catalogue is down.')).not.toBeInTheDocument()
  })

  it('waits for the equipment names when they arrive after the queue', async () => {
    server.use(
      http.get(TYPES_PATH, async () => {
        await delay(200)
        return HttpResponse.json([
          {
            id: 1,
            name: 'Laser Pointer',
            description: null,
            total_quantity: 5,
            venue_id: null,
            store_name: null,
          },
        ])
      }),
    )
    answerQueueWith([queued('Rooftop Social', 4)])
    openStaffHome(MOCK_ACCOUNTS.technicalSupport)

    expect(within(await queue()).getByRole('listitem')).toHaveTextContent('Laser Pointer × 3')
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
    ['the Safety Officer', MOCK_ACCOUNTS.safetyOfficer],
  ])('shows %s no queue, and asks for neither it nor the types (AC6)', async (_role, account) => {
    const requests = recordRequests()
    openStaffHome(account)

    expect(await screen.findByRole('heading', { level: 1, name: 'Staff home' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: QUEUE_NAME })).not.toBeInTheDocument()
    const asked = requests.map((request) => new URL(request.url).pathname)
    expect(asked).not.toContain(AWAITING_PATH)
    expect(asked).not.toContain(TYPES_PATH)
  })
})
