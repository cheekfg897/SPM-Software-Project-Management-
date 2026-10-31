import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES, staffEventPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import {
  EMPTY_QUEUE_MESSAGE,
  eventByReference,
  NOT_A_COORDINATOR_MESSAGE,
} from '@/mocks/handlers/lead'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

const QUEUE_URL = '/api/events/requests/unassigned'

/** The queue entry for one request, found by the name its heading gives it. */
async function findRequest(name: string) {
  return within(await screen.findByRole('article', { name }))
}

/** Another Lead assigns the request in the mock backend while this Lead's page still shows it. */
function assignedByAnotherLead(reference: string) {
  const event = eventByReference(reference)
  if (event === undefined) {
    throw new Error(`The mock backend has no event ${reference}`)
  }
  event.coordinator_id = MOCK_ACCOUNTS.coordinator.id
}

/** How many times the page read the queue. */
function queueReadsIn(requests: Request[]): number {
  return requests.filter(
    (request) => request.method === 'GET' && new URL(request.url).pathname === QUEUE_URL,
  ).length
}

describe('SCRUM-95 the Lead queue screen', () => {
  it('shows each queued request with its name, date, time, attendance and submission time', async () => {
    renderApp(ROUTES.LEAD_QUEUE, { session: mockSessionFor(MOCK_ACCOUNTS.lead) })

    const summit = await findRequest('Annual Partner Summit')
    expect(summit.getByText('12 Nov 2026')).toBeInTheDocument()
    expect(summit.getByText('9:00 am – 5:00 pm')).toBeInTheDocument()
    expect(summit.getByText('250')).toBeInTheDocument()
    expect(summit.getByText('1 Oct 2026, 9:30 am')).toBeInTheDocument()
    expect(summit.getByText('EVR-MOCK0001')).toBeInTheDocument()
    const launch = await findRequest('Product Launch Evening')
    expect(launch.getByText('20 Nov 2026')).toBeInTheDocument()
    expect(launch.getByText('6:00 pm – 9:30 pm')).toBeInTheDocument()
    expect(launch.getByText('120')).toBeInTheDocument()
    expect(launch.getByText('2 Oct 2026, 2:05 pm')).toBeInTheDocument()
  })

  it("shows each queued request's status, as every list does (SCRUM-24 AC8)", async () => {
    renderApp(ROUTES.LEAD_QUEUE, { session: mockSessionFor(MOCK_ACCOUNTS.lead) })

    const summit = await findRequest('Annual Partner Summit')
    expect(summit.getByText('Status').nextElementSibling).toHaveTextContent('Submitted')
    const launch = await findRequest('Product Launch Evening')
    expect(launch.getByText('Status').nextElementSibling).toHaveTextContent('Submitted')
  })

  it('opens the read-only record of a request waiting in the queue (SCRUM-24 AC10)', async () => {
    const { user, router } = renderApp(ROUTES.LEAD_QUEUE, {
      session: mockSessionFor(MOCK_ACCOUNTS.lead),
    })

    const launch = await findRequest('Product Launch Evening')
    await user.click(launch.getByRole('link', { name: 'Open the event record' }))

    expect(router.state.location.pathname).toBe(staffEventPath('EVR-MOCK0002'))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Product Launch Evening' }),
    ).toBeInTheDocument()
    expect(screen.getByText('No coordinator is assigned yet.')).toBeInTheDocument()
  })

  it('takes an assigned request out of the list because the queue is read again', async () => {
    const requests = recordRequests()
    const { user } = renderApp(ROUTES.LEAD_QUEUE, {
      session: mockSessionFor(MOCK_ACCOUNTS.lead),
    })
    const summit = await findRequest('Annual Partner Summit')

    await user.type(summit.getByLabelText(/^Coordinator email/), MOCK_ACCOUNTS.coordinator.email)
    await user.click(summit.getByRole('button', { name: /^Assign/ }))

    await waitFor(() =>
      expect(
        screen.queryByRole('article', { name: 'Annual Partner Summit' }),
      ).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('article', { name: 'Product Launch Evening' })).toBeInTheDocument()
    expect(queueReadsIn(requests)).toBe(2)
    const post = requests.find((request) => request.method === 'POST')
    expect(await post?.json()).toEqual({ coordinator_email: MOCK_ACCOUNTS.coordinator.email })
  })

  it('shows the backend message beside the email field when no coordinator has that address', async () => {
    const { user } = renderApp(ROUTES.LEAD_QUEUE, {
      session: mockSessionFor(MOCK_ACCOUNTS.lead),
    })
    const summit = await findRequest('Annual Partner Summit')

    await user.type(summit.getByLabelText(/^Coordinator email/), 'nobody@example.com')
    await user.click(summit.getByRole('button', { name: /^Assign/ }))

    const field = await summit.findByLabelText(/^Coordinator email/)
    await waitFor(() => expect(field).toHaveAccessibleDescription(NOT_A_COORDINATOR_MESSAGE))
    expect(field).toBeInvalid()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('article', { name: 'Annual Partner Summit' })).toBeInTheDocument()
  })

  it('shows the backend message in an alert when the assignment fails for another reason', async () => {
    server.use(
      http.post('/api/events/requests/:reference/coordinator', () =>
        HttpResponse.json(
          { error: 'conflict', message: 'This event request already has a coordinator.' },
          { status: 409 },
        ),
      ),
    )
    const { user } = renderApp(ROUTES.LEAD_QUEUE, {
      session: mockSessionFor(MOCK_ACCOUNTS.lead),
    })
    const summit = await findRequest('Annual Partner Summit')

    await user.type(summit.getByLabelText(/^Coordinator email/), MOCK_ACCOUNTS.coordinator.email)
    await user.click(summit.getByRole('button', { name: /^Assign/ }))

    expect(await summit.findByRole('alert')).toHaveTextContent(
      'This event request already has a coordinator.',
    )
    // The request is still queued, so its own card says why and nothing above repeats it.
    expect(screen.getAllByRole('alert')).toHaveLength(1)
  })

  it('reads the queue again when another Lead assigned the request first, and says why it left (SCRUM-95 AC4)', async () => {
    const requests = recordRequests()
    const { user } = renderApp(ROUTES.LEAD_QUEUE, {
      session: mockSessionFor(MOCK_ACCOUNTS.lead),
    })
    const summit = await findRequest('Annual Partner Summit')
    assignedByAnotherLead('EVR-MOCK0001')

    await user.type(summit.getByLabelText(/^Coordinator email/), MOCK_ACCOUNTS.coordinator.email)
    await user.click(summit.getByRole('button', { name: /^Assign/ }))

    await waitFor(() =>
      expect(
        screen.queryByRole('article', { name: 'Annual Partner Summit' }),
      ).not.toBeInTheDocument(),
    )
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Annual Partner Summit (EVR-MOCK0001)')
    expect(alert).toHaveTextContent('This event request already has a coordinator.')
    expect(queueReadsIn(requests)).toBe(2)
  })

  it('clears that message once the Lead assigns another request', async () => {
    const { user } = renderApp(ROUTES.LEAD_QUEUE, {
      session: mockSessionFor(MOCK_ACCOUNTS.lead),
    })
    const summit = await findRequest('Annual Partner Summit')
    assignedByAnotherLead('EVR-MOCK0001')
    await user.type(summit.getByLabelText(/^Coordinator email/), MOCK_ACCOUNTS.coordinator.email)
    await user.click(summit.getByRole('button', { name: /^Assign/ }))
    await screen.findByRole('alert')

    const launch = await findRequest('Product Launch Evening')
    await user.type(launch.getByLabelText(/^Coordinator email/), MOCK_ACCOUNTS.coordinator.email)
    await user.click(launch.getByRole('button', { name: /^Assign/ }))

    await waitFor(() =>
      expect(
        screen.queryByRole('article', { name: 'Product Launch Evening' }),
      ).not.toBeInTheDocument(),
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the backend message instead of a spinner when the queue is empty', async () => {
    server.use(
      http.get(QUEUE_URL, () =>
        HttpResponse.json({ event_requests: [], message: EMPTY_QUEUE_MESSAGE }),
      ),
    )
    renderApp(ROUTES.LEAD_QUEUE, { session: mockSessionFor(MOCK_ACCOUNTS.lead) })

    expect(await screen.findByText(EMPTY_QUEUE_MESSAGE)).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('shows the backend message when the queue cannot be read', async () => {
    server.use(
      http.get(QUEUE_URL, () =>
        HttpResponse.json(
          { error: 'server_error', message: 'Something went wrong.' },
          { status: 500 },
        ),
      ),
    )
    renderApp(ROUTES.LEAD_QUEUE, { session: mockSessionFor(MOCK_ACCOUNTS.lead) })

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong.')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('names the request in each email field and Assign button, so rows can be told apart', async () => {
    renderApp(ROUTES.LEAD_QUEUE, { session: mockSessionFor(MOCK_ACCOUNTS.lead) })

    expect(
      await screen.findByLabelText('Coordinator email for Annual Partner Summit'),
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText('Coordinator email for Product Launch Evening'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Assign Annual Partner Summit' })).toBeInTheDocument()
  })

  it('reads the queue again when Try again is pressed after a failure', async () => {
    server.use(
      http.get(
        QUEUE_URL,
        () =>
          HttpResponse.json(
            { error: 'server_error', message: 'Something went wrong.' },
            { status: 500 },
          ),
        { once: true },
      ),
    )
    const { user } = renderApp(ROUTES.LEAD_QUEUE, {
      session: mockSessionFor(MOCK_ACCOUNTS.lead),
    })
    await user.click(await screen.findByRole('button', { name: 'Try again' }))

    expect(
      await screen.findByRole('article', { name: 'Annual Partner Summit' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('offers an Event Coordinator neither the queue nor the assign control (AC6)', async () => {
    const requests = recordRequests()
    const { router } = renderApp(ROUTES.LEAD_QUEUE, {
      session: mockSessionFor(MOCK_ACCOUNTS.coordinator),
    })

    await waitFor(() => expect(router.state.location.pathname).not.toBe(ROUTES.LEAD_QUEUE))
    expect(router.state.location.pathname).toBe(ROUTES.STAFF_HOME)
    expect(screen.queryByRole('heading', { name: 'Unassigned requests' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/^Coordinator email/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Assign/ })).not.toBeInTheDocument()
    expect(requests.some((request) => new URL(request.url).pathname === QUEUE_URL)).toBe(false)
  })

  it('sends a visitor who is signed out to the staff log-in page', async () => {
    const { router } = renderApp(ROUTES.LEAD_QUEUE)

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN))
  })
})
