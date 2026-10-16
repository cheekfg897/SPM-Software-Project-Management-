import { screen, waitFor, within } from '@testing-library/react'

import { saveDraftEventRequest } from '@/features/eventRequests/api'

import { editDraftPath, ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'
import { sendRequestsAs } from '@/test/sendRequestsAs'

/**
 * SCRUM-20: an Event Organiser goes back to one of their drafts, changes it and saves it again,
 * or submits it (ADR-0024). The mock's draft EVR-3HD8PL2W, "Volunteer Thank-You Dinner", has
 * only a name; EVR-H2PL8R6K is a colleague's draft. The mock's "today" is Monday 2026-10-05.
 */

const ORGANISER = mockSessionFor(MOCK_ACCOUNTS.organiser)
const OWN_DRAFT = 'EVR-3HD8PL2W'
const DRAFT_URL = `/api/events/requests/drafts/${OWN_DRAFT}`

type App = ReturnType<typeof renderApp>

async function openOwnDraft(): Promise<App> {
  const app = renderApp(editDraftPath(OWN_DRAFT), { session: ORGANISER })
  await waitFor(() =>
    expect(screen.getByLabelText('Event name')).toHaveValue('Volunteer Thank-You Dinner'),
  )
  return app
}

async function fill(app: App, label: string, value: string) {
  await app.user.type(screen.getByLabelText(label), value)
}

function firstRow(): HTMLElement {
  const rows = within(screen.getByRole('list', { name: 'Your event requests' })).getAllByRole(
    'listitem',
  )
  const first = rows[0]
  if (first === undefined) {
    throw new Error('The list has no rows.')
  }
  return first
}

describe('SCRUM-20 editing a draft: opening it', () => {
  it('opens the draft with what was saved on it, and registration as saved', async () => {
    await openOwnDraft()

    expect(screen.getByRole('heading', { level: 1, name: 'Edit draft' })).toBeInTheDocument()
    expect(screen.getByLabelText('Date')).toHaveValue('')
    expect(screen.getByRole('radio', { name: 'No' })).toBeChecked()
  })

  it('shows what a draft already holds, its times to the minute and registration as saved', async () => {
    sendRequestsAs(ORGANISER.accessToken)
    const saved = await saveDraftEventRequest({
      name: 'Spring Fair',
      proposed_date: '2026-11-20',
      start_time: '10:00',
      end_time: '16:30',
      expected_attendance: 80,
      registration_required: true,
    })
    sendRequestsAs(null)

    renderApp(editDraftPath(saved.reference), { session: ORGANISER })

    await waitFor(() => expect(screen.getByLabelText('Event name')).toHaveValue('Spring Fair'))
    expect(screen.getByLabelText('Date')).toHaveValue('2026-11-20')
    expect(screen.getByLabelText('Starts')).toHaveValue('10:00')
    expect(screen.getByLabelText('Ends')).toHaveValue('16:30')
    expect(screen.getByLabelText('Expected attendance')).toHaveValue(80)
    expect(screen.getByRole('radio', { name: 'Yes' })).toBeChecked()
  })

  it('says it is loading until the draft arrives', async () => {
    renderApp(editDraftPath(OWN_DRAFT), { session: ORGANISER })

    expect(screen.getByText('Loading your draft…')).toBeInTheDocument()
    await screen.findByLabelText('Event name')
    expect(screen.queryByText('Loading your draft…')).not.toBeInTheDocument()
  })

  it("shows the backend's message for a draft that can't be opened, such as a colleague's", async () => {
    renderApp(editDraftPath('EVR-H2PL8R6K'), { session: ORGANISER })

    expect(await screen.findByRole('alert')).toHaveTextContent('Event request not found.')
    expect(screen.queryByLabelText('Event name')).not.toBeInTheDocument()
  })
})

describe('SCRUM-20 editing a draft: saving it', () => {
  it('saves every field again, an emptied one as null, and lists the changed draft', async () => {
    const requests = recordRequests()
    const app = await openOwnDraft()
    await app.user.clear(screen.getByLabelText('Event name'))
    await fill(app, 'Event name', 'Thank-You Dinner')
    await fill(app, 'Purpose', 'Thanking volunteers')

    await app.user.click(screen.getByRole('button', { name: 'Save draft' }))

    expect(await screen.findByRole('heading', { name: 'Thank-You Dinner' })).toBeInTheDocument()
    expect(app.router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME)
    const patches = requests.filter((request) => request.method === 'PATCH')
    expect(patches.map((request) => new URL(request.url).pathname)).toEqual([DRAFT_URL])
    expect(await patches[0]?.json()).toEqual({
      name: 'Thank-You Dinner',
      purpose: 'Thanking volunteers',
      description: null,
      proposed_date: null,
      end_date: null,
      start_time: null,
      end_time: null,
      expected_attendance: null,
      venue_requirements: null,
      accessibility_needs: null,
      equipment_requirements: null,
      registration_required: false,
    })
  })
})

describe('SCRUM-20 editing a draft: submitting it', () => {
  it('saves the changes, submits the draft and lists it as submitted', async () => {
    const requests = recordRequests()
    const app = await openOwnDraft()
    await fill(app, 'Date', '2026-11-20')
    await fill(app, 'Starts', '18:30')
    await fill(app, 'Ends', '22:00')
    await fill(app, 'Expected attendance', '60')

    await app.user.click(screen.getByRole('button', { name: 'Submit request' }))

    await waitFor(() => expect(app.router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME))
    expect(await screen.findByRole('heading', { name: 'Volunteer Thank-You Dinner' })).toBeVisible()
    expect(firstRow()).not.toHaveTextContent('Draft')
    const calls = requests
      .filter((request) => request.method !== 'GET')
      .map((request) => `${request.method} ${new URL(request.url).pathname}`)
    expect(calls).toEqual([`PATCH ${DRAFT_URL}`, `POST ${DRAFT_URL}/submit`])
  })

  it("shows the backend's message for a date in the past under the date of a resumed draft", async () => {
    const app = await openOwnDraft()
    await fill(app, 'Date', '2026-10-04')
    await fill(app, 'Starts', '18:30')
    await fill(app, 'Ends', '22:00')
    await fill(app, 'Expected attendance', '60')

    await app.user.click(screen.getByRole('button', { name: 'Submit request' }))

    expect(await screen.findByLabelText('Date')).toHaveAccessibleDescription(
      'Proposed date cannot be in the past.',
    )
    expect(app.router.state.location.pathname).toBe(editDraftPath(OWN_DRAFT))
  })

  it("shows the backend's message under each detail a submission still needs", async () => {
    const app = await openOwnDraft()

    await app.user.click(screen.getByRole('button', { name: 'Submit request' }))

    for (const label of ['Date', 'Starts', 'Ends', 'Expected attendance']) {
      expect(await screen.findByLabelText(label)).toHaveAccessibleDescription(
        'Missing data for required field.',
      )
    }
    await waitFor(() => expect(screen.getByLabelText('Date')).toHaveFocus())
    expect(app.router.state.location.pathname).toBe(editDraftPath(OWN_DRAFT))
  })
})

describe('SCRUM-20 editing a draft: one refusal at a time', () => {
  it("after a refused submission, a refused save shows only the save's message", async () => {
    const app = await openOwnDraft()
    await app.user.click(screen.getByRole('button', { name: 'Submit request' }))
    await screen.findAllByText('Missing data for required field.')
    await app.user.clear(screen.getByLabelText('Event name'))
    await fill(app, 'Event name', '   ')

    await app.user.click(screen.getByRole('button', { name: 'Save draft' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Date')).toHaveAttribute('aria-invalid', 'false'),
    )
    expect(screen.getByLabelText('Event name')).toHaveAccessibleDescription(
      'Event name must not be blank.',
    )
  })

  it("after a refused save, a refused submission shows only the submission's messages", async () => {
    const app = await openOwnDraft()
    await app.user.clear(screen.getByLabelText('Event name'))
    await fill(app, 'Event name', '   ')
    await app.user.click(screen.getByRole('button', { name: 'Save draft' }))
    await screen.findByText('Event name must not be blank.')
    await app.user.clear(screen.getByLabelText('Event name'))
    await fill(app, 'Event name', 'Volunteer Thank-You Dinner')

    await app.user.click(screen.getByRole('button', { name: 'Submit request' }))

    expect(await screen.findByLabelText('Date')).toHaveAccessibleDescription(
      'Missing data for required field.',
    )
    expect(screen.getByLabelText('Event name')).toHaveAttribute('aria-invalid', 'false')
  })
})

describe('SCRUM-20 editing a draft: who may open it', () => {
  it('sends a visitor to log in, and back here afterwards', () => {
    const { router } = renderApp(editDraftPath(OWN_DRAFT))

    expect(router.state.location.pathname).toBe(ROUTES.LOGIN)
    expect(router.state.location.search).toContain(encodeURIComponent(editDraftPath(OWN_DRAFT)))
  })

  it('sends an attendee to their own home', () => {
    const { router } = renderApp(editDraftPath(OWN_DRAFT), {
      session: mockSessionFor(MOCK_ACCOUNTS.attendee),
    })

    expect(router.state.location.pathname).not.toBe(editDraftPath(OWN_DRAFT))
  })
})
