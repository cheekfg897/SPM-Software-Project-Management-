import { screen, waitFor, within } from '@testing-library/react'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { coordinatorEventPath, editEventPath, organiserRequestPath, ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { serveRecordInStatus, statusShownFor } from '../test/recordPage'

/**
 * SCRUM-33 AC1 to AC3: the assigned coordinator changes an event's details, is told which
 * changes were significant and that the arrangements will be reassessed, and sees the backend's
 * refusals under the fields they are about (ADR-0025, ADR-0079). The mock's Partner Summit
 * (EVR-7K2M9QXA) is Chloe's, under review: 12 Nov, 9:00 am to 5:00 pm, 250 expected. Her
 * Year-End Town Hall (EVR-BOOK0102) is Confirmed, so it changes only through a change request
 * (AC8, ADR-0101). The mock's "today" is 5 Oct 2026.
 */

const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
const ORGANISER = mockSessionFor(MOCK_ACCOUNTS.organiser)
const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
const TOWN_HALL = 'EVR-BOOK0102'
/** Every status before Confirmed, which the backend lets an edit through (AC8, ADR-0101). */
const EDIT_OFFERED_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
]
/** Every other status, built from the statuses so one added later is checked too. */
const EDIT_NOT_OFFERED_STATUSES = Object.values(EVENT_REQUEST_STATUS).filter(
  (status) => !EDIT_OFFERED_STATUSES.includes(status),
)

type App = ReturnType<typeof renderApp>

async function openEditForm(reference = PARTNER_SUMMIT): Promise<App> {
  const app = renderApp(editEventPath(reference), { session: COORDINATOR })
  await screen.findByRole('button', { name: 'Save changes' })
  return app
}

async function replace(app: App, label: string, value: string) {
  const field = screen.getByLabelText(label)
  await app.user.clear(field)
  if (value !== '') {
    await app.user.type(field, value)
  }
}

async function save(app: App) {
  await app.user.click(screen.getByRole('button', { name: 'Save changes' }))
}

/** The PATCH bodies sent to the backend. */
async function sentEdits(requests: Request[]): Promise<unknown[]> {
  const edits = requests.filter((request) => request.method === 'PATCH')
  return Promise.all(edits.map((request) => request.json()))
}

describe('SCRUM-33 AC1 the edit form', () => {
  it('opens with what the event holds, its times to the minute', async () => {
    await openEditForm()

    expect(screen.getByRole('heading', { level: 1, name: 'Edit event details' })).toBeVisible()
    expect(screen.getByText('Partner Summit')).toBeInTheDocument()
    expect(screen.getByLabelText('Programme notes')).toHaveValue(
      'Keynote at 9:30, breakout rooms after lunch.',
    )
    expect(screen.getByLabelText('Date')).toHaveValue('2026-11-12')
    expect(screen.getByLabelText('End date')).toHaveValue('2026-11-12')
    expect(screen.getByLabelText('Starts')).toHaveValue('09:00')
    expect(screen.getByLabelText('Ends')).toHaveValue('17:00')
    expect(screen.getByLabelText('Expected attendance')).toHaveValue(250)
    expect(screen.getByLabelText('Venue requirements')).toHaveValue(
      'A main hall for 250 and four breakout rooms.',
    )
    expect(screen.getByLabelText('Description')).toHaveValue('')
    expect(screen.getByLabelText('Planning notes')).toHaveValue('')
  })

  it('offers no field for what is not the coordinator to change (AC3)', async () => {
    await openEditForm()

    for (const label of ['Event name', 'Purpose', 'Venue', 'Equipment']) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument()
    }
  })

  it('saves a change to the notes with no further step, and says it is not significant', async () => {
    const app = await openEditForm()
    const requests = recordRequests()

    await replace(app, 'Description', 'Two days with our partners.')
    await save(app)

    const saved = await screen.findByRole('region', { name: 'Saved' })
    expect(await sentEdits(requests)).toEqual([{ description: 'Two days with our partners.' }])
    expect(within(saved).getByRole('heading', { level: 3 })).toHaveTextContent(
      'Description changed',
    )
    expect(within(saved).queryByText('Significant change')).not.toBeInTheDocument()
    expect(within(saved).queryByText(/reassessed/)).not.toBeInTheDocument()
  })
})

describe('SCRUM-33 AC2 a significant change', () => {
  it('sends only what changed, marks it significant and says the arrangements will be reassessed', async () => {
    const app = await openEditForm()
    const requests = recordRequests()

    await replace(app, 'Expected attendance', '300')
    await save(app)

    const saved = await screen.findByRole('region', { name: 'Saved' })
    expect(await sentEdits(requests)).toEqual([{ expected_attendance: 300 }])
    expect(saved).toHaveTextContent('Expected attendance changed')
    expect(within(saved).getByText('Before').nextElementSibling).toHaveTextContent('250')
    expect(within(saved).getByText('After').nextElementSibling).toHaveTextContent('300')
    expect(within(saved).getByText('Significant change')).toBeInTheDocument()
    expect(
      within(saved).getByText(
        'A significant change means the arrangements already made for this event will be reassessed.',
      ),
    ).toBeInTheDocument()
  })

  it('shows the event as the backend now holds it once saved', async () => {
    const app = await openEditForm()

    await replace(app, 'Date', '2026-11-19')
    await save(app)

    expect(await screen.findByText('Thu, 19 Nov · 9:00 am – 5:00 pm')).toBeInTheDocument()
  })

  it('shows the end date the backend moved with the date', async () => {
    const app = await openEditForm()

    await replace(app, 'Date', '2026-11-19')
    await save(app)

    const saved = await screen.findByRole('region', { name: 'Saved' })
    const changes = within(saved).getAllByRole('heading', { level: 3 })
    expect(changes.map((change) => change.textContent)).toEqual([
      'Proposed date changed',
      'End date changed',
    ])
  })

  it('says so when nothing was changed', async () => {
    const app = await openEditForm()

    await save(app)

    const saved = await screen.findByRole('region', { name: 'Saved' })
    expect(saved).toHaveTextContent('Nothing changed: the event already held these details.')
  })

  it('links back to the event, where the history shows the change', async () => {
    const app = await openEditForm()

    await replace(app, 'Expected attendance', '300')
    await save(app)
    const saved = await screen.findByRole('region', { name: 'Saved' })
    await app.user.click(within(saved).getByRole('link', { name: 'Back to the event' }))

    expect(app.router.state.location.pathname).toBe(coordinatorEventPath(PARTNER_SUMMIT))
    const history = await screen.findByRole('region', { name: 'History' })
    expect(await within(history).findByText('5 Oct, 12:00 pm · Chloe Lim')).toBeInTheDocument()
  })
})

describe('SCRUM-33 AC9 a significant change in Safety Review', () => {
  it('shows the event back in Approved once the change unsettles its venue', async () => {
    const app = renderApp(editEventPath('EVR-PLAN0004'), {
      session: mockSessionFor(MOCK_ACCOUNTS.planningCoordinator),
    })
    await screen.findByRole('button', { name: 'Save changes' })

    await replace(app, 'Venue requirements', 'Step-free stage.')
    await save(app)
    const saved = await screen.findByRole('region', { name: 'Saved' })
    await app.user.click(within(saved).getByRole('link', { name: 'Back to the event' }))

    await screen.findByRole('region', { name: 'About the event' })
    expect(statusShownFor('EVR-PLAN0004')).toBe('Approved')
  })
})

describe("SCRUM-33 the backend's refusals", () => {
  it('shows a field message under its field and moves to it', async () => {
    const app = await openEditForm()

    await replace(app, 'Date', '2026-10-01')
    await save(app)

    const date = screen.getByLabelText('Date')
    await waitFor(() => expect(date).toHaveAccessibleDescription(/cannot be in the past/))
    expect(date).toHaveFocus()
    expect(screen.queryByRole('region', { name: 'Saved' })).not.toBeInTheDocument()
  })

  it("shows the backend's message for a Confirmed event, which changes only through a change request (AC8)", async () => {
    const app = await openEditForm(TOWN_HALL)

    await replace(app, 'Description', 'A short one.')
    await save(app)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A confirmed event can only be changed through a change request.',
    )
    expect(screen.queryByRole('region', { name: 'Saved' })).not.toBeInTheDocument()
  })

  it('reads the event again after a refused save, in case it moved on', async () => {
    const app = await openEditForm(TOWN_HALL)
    const requests = recordRequests()

    await replace(app, 'Description', 'A short one.')
    await save(app)

    await screen.findByRole('alert')
    await waitFor(() => {
      const methods = requests.map(
        (request) => `${request.method} ${new URL(request.url).pathname}`,
      )
      expect(methods).toEqual([
        `PATCH /api/events/requests/${TOWN_HALL}`,
        `GET /api/events/requests/${TOWN_HALL}`,
      ])
    })
  })

  it("can't open another coordinator's event, even by its link", async () => {
    renderApp(editEventPath('EVR-W9CR5E7M'), { session: COORDINATOR })

    expect(await screen.findByRole('alert')).toHaveTextContent('Event request not found.')
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
  })

  it('says it is loading until the event arrives', () => {
    renderApp(editEventPath(PARTNER_SUMMIT), { session: COORDINATOR })

    expect(screen.getByRole('status')).toHaveTextContent('Loading the event')
  })
})

describe('SCRUM-33 who reaches the edit form', () => {
  it.each(EDIT_OFFERED_STATUSES)(
    "links to it from the coordinator's record of an event that is %s",
    async (status) => {
      await serveRecordInStatus(MOCK_ACCOUNTS.coordinator, PARTNER_SUMMIT, status)
      renderApp(coordinatorEventPath(PARTNER_SUMMIT), { session: COORDINATOR })

      expect(await screen.findByRole('link', { name: 'Edit event details' })).toHaveAttribute(
        'href',
        editEventPath(PARTNER_SUMMIT),
      )
    },
  )

  it.each(EDIT_NOT_OFFERED_STATUSES)(
    'offers no edit, and no Edit details section, for an event that is %s (AC8)',
    async (status) => {
      await serveRecordInStatus(MOCK_ACCOUNTS.coordinator, PARTNER_SUMMIT, status)
      renderApp(coordinatorEventPath(PARTNER_SUMMIT), { session: COORDINATOR })

      await screen.findByRole('region', { name: 'About the event' })
      expect(screen.queryByRole('region', { name: 'Edit details' })).not.toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'Edit event details' })).not.toBeInTheDocument()
    },
  )

  it("gives the organiser's record no link to it", async () => {
    renderApp(organiserRequestPath(PARTNER_SUMMIT), { session: ORGANISER })

    await screen.findByRole('region', { name: 'About the event' })
    expect(screen.queryByRole('link', { name: 'Edit event details' })).not.toBeInTheDocument()
  })

  it('sends an organiser who opens it to their own home', () => {
    const { router } = renderApp(editEventPath(PARTNER_SUMMIT), { session: ORGANISER })

    expect(router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME)
  })
})
