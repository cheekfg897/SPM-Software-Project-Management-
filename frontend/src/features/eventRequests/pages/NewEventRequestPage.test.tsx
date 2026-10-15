import { screen, waitFor, within } from '@testing-library/react'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-19: an Event Organiser submits a new event request from the web app. Every check is
 * the backend's (the mock words them as it does); the page shows its messages where they
 * belong. The mock's "today" is Monday 2026-10-05.
 */

const ORGANISER = mockSessionFor(MOCK_ACCOUNTS.organiser)
const SUBMIT_URL = '/api/events/requests'

type App = ReturnType<typeof renderApp>

/** Type into the field with this label, as a person would. */
async function fill(app: App, label: string, value: string) {
  await app.user.type(screen.getByLabelText(label), value)
}

/** The fields every submission needs, filled in for an event in November. */
async function fillRequired(app: App) {
  await fill(app, 'Event name', 'Harbour Lights Gala')
  await fill(app, 'Date', '2026-11-20')
  await fill(app, 'Starts', '19:00')
  await fill(app, 'Ends', '23:00')
  await fill(app, 'Expected attendance', '300')
}

async function submit(app: App) {
  await app.user.click(screen.getByRole('button', { name: 'Submit request' }))
}

/** The JSON bodies of the submissions sent so far. */
async function submittedBodies(requests: Request[]): Promise<unknown[]> {
  const submissions = requests.filter(
    (request) => request.method === 'POST' && new URL(request.url).pathname === SUBMIT_URL,
  )
  return Promise.all(submissions.map((request) => request.json() as Promise<unknown>))
}

describe('SCRUM-19 new event request: the form', () => {
  it('asks for everything SCRUM-19 lists, with registration set to No', () => {
    renderApp(ROUTES.NEW_EVENT_REQUEST, { session: ORGANISER })

    for (const label of [
      'Event name',
      'Purpose',
      'Description',
      'Date',
      'Starts',
      'Ends',
      'Ends on a later day',
      'Expected attendance',
      'Venue requirements',
      'Accessibility needs',
      'Equipment requirements',
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
    const registration = screen.getByRole('radiogroup', { name: 'Do attendees need to register?' })
    expect(within(registration).getByRole('radio', { name: 'No' })).toBeChecked()
  })
})

describe('SCRUM-19 new event request: submitting', () => {
  it('sends what was filled in, then shows it at the top of the list as Submitted', async () => {
    const requests = recordRequests()
    const app = renderApp(ROUTES.NEW_EVENT_REQUEST, { session: ORGANISER })
    await fillRequired(app)
    await fill(app, 'Purpose', 'Fundraiser')
    await fill(app, 'Accessibility needs', 'Step-free access')
    await app.user.click(screen.getByRole('radio', { name: 'Yes' }))

    await submit(app)

    expect(await screen.findByRole('heading', { name: 'Harbour Lights Gala' })).toBeInTheDocument()
    expect(app.router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME)
    const firstRow = within(screen.getByRole('list', { name: 'Your event requests' })).getAllByRole(
      'listitem',
    )[0]
    expect(firstRow).toHaveTextContent('Harbour Lights Gala')
    expect(firstRow).toHaveTextContent('Submitted')
    expect(firstRow).toHaveTextContent('EVR-NEW00001')
    expect(await submittedBodies(requests)).toEqual([
      {
        name: 'Harbour Lights Gala',
        purpose: 'Fundraiser',
        proposed_date: '2026-11-20',
        start_time: '19:00',
        end_time: '23:00',
        expected_attendance: 300,
        accessibility_needs: 'Step-free access',
        registration_required: true,
      },
    ])
  })

  it("shows the backend's message under each missing field, keeping what was typed", async () => {
    const app = renderApp(ROUTES.NEW_EVENT_REQUEST, { session: ORGANISER })
    await fill(app, 'Event name', 'Just a name')

    await submit(app)

    for (const label of ['Date', 'Starts', 'Ends', 'Expected attendance']) {
      expect(await screen.findByLabelText(label)).toHaveAccessibleDescription(
        'Missing data for required field.',
      )
    }
    expect(screen.getByLabelText('Event name')).toHaveValue('Just a name')
    expect(app.router.state.location.pathname).toBe(ROUTES.NEW_EVENT_REQUEST)
  })

  it('moves to the first field the backend refused, so the message is seen', async () => {
    const app = renderApp(ROUTES.NEW_EVENT_REQUEST, { session: ORGANISER })
    await fill(app, 'Event name', 'Just a name')

    await submit(app)

    await waitFor(() => expect(screen.getByLabelText('Date')).toHaveFocus())
  })

  it("shows the backend's message for a date in the past under the date", async () => {
    const app = renderApp(ROUTES.NEW_EVENT_REQUEST, { session: ORGANISER })
    await fillRequired(app)
    await app.user.clear(screen.getByLabelText('Date'))
    await fill(app, 'Date', '2026-10-04')

    await submit(app)

    expect(await screen.findByLabelText('Date')).toHaveAccessibleDescription(
      'Proposed date cannot be in the past.',
    )
  })

  it("shows the backend's message for an event that ends before it starts under its end", async () => {
    const app = renderApp(ROUTES.NEW_EVENT_REQUEST, { session: ORGANISER })
    await fillRequired(app)
    await app.user.clear(screen.getByLabelText('Ends'))
    await fill(app, 'Ends', '18:00')

    await submit(app)

    expect(await screen.findByLabelText('Ends')).toHaveAccessibleDescription(
      'Event must end after it starts.',
    )
  })

  it('shows a refusal that is not about one field above the form', async () => {
    const app = renderApp(ROUTES.NEW_EVENT_REQUEST, {
      session: mockSessionFor(MOCK_ACCOUNTS.unlinkedOrganiser),
    })
    await fillRequired(app)

    await submit(app)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your account is not linked to a client organisation yet.',
    )
  })
})

describe('SCRUM-20 new event request: saving a draft', () => {
  it('saves what was typed as a draft, even with only a name, and lists it as a draft', async () => {
    const requests = recordRequests()
    const app = renderApp(ROUTES.NEW_EVENT_REQUEST, { session: ORGANISER })
    await fill(app, 'Event name', 'Spring Fair')

    await app.user.click(screen.getByRole('button', { name: 'Save as draft' }))

    expect(await screen.findByRole('heading', { name: 'Spring Fair' })).toBeInTheDocument()
    expect(app.router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME)
    const firstRow = within(screen.getByRole('list', { name: 'Your event requests' })).getAllByRole(
      'listitem',
    )[0]
    expect(firstRow).toHaveTextContent('Spring Fair')
    expect(firstRow).toHaveTextContent('Draft')
    const drafts = requests.filter(
      (request) => new URL(request.url).pathname === '/api/events/requests/drafts',
    )
    expect(await Promise.all(drafts.map((request) => request.json() as Promise<unknown>))).toEqual([
      { name: 'Spring Fair', registration_required: false },
    ])
  })

  it("shows the backend's message when a draft has no name", async () => {
    const app = renderApp(ROUTES.NEW_EVENT_REQUEST, { session: ORGANISER })
    await fill(app, 'Event name', '   ')

    await app.user.click(screen.getByRole('button', { name: 'Save as draft' }))

    expect(await screen.findByLabelText('Event name')).toHaveAccessibleDescription(
      'Event name must not be blank.',
    )
  })
})

describe('SCRUM-20 new event request: one refusal at a time', () => {
  it("after a refused submission, a refused draft shows only the draft's message", async () => {
    const app = renderApp(ROUTES.NEW_EVENT_REQUEST, { session: ORGANISER })
    await fill(app, 'Event name', '   ')
    await submit(app)
    await screen.findAllByText('Missing data for required field.')

    await app.user.click(screen.getByRole('button', { name: 'Save as draft' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Date')).toHaveAttribute('aria-invalid', 'false'),
    )
    expect(screen.getByLabelText('Event name')).toHaveAccessibleDescription(
      'Event name must not be blank.',
    )
  })
})

describe('SCRUM-19 new event request: who may open it', () => {
  it('sends a visitor to log in, and back here afterwards', () => {
    const { router } = renderApp(ROUTES.NEW_EVENT_REQUEST)

    expect(router.state.location.pathname).toBe(ROUTES.LOGIN)
    expect(router.state.location.search).toContain(encodeURIComponent(ROUTES.NEW_EVENT_REQUEST))
  })

  it('sends an attendee to their own home', () => {
    const { router } = renderApp(ROUTES.NEW_EVENT_REQUEST, {
      session: mockSessionFor(MOCK_ACCOUNTS.attendee),
    })

    expect(router.state.location.pathname).not.toBe(ROUTES.NEW_EVENT_REQUEST)
  })
})
