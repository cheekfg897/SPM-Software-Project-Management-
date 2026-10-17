import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { ALREADY_ASSIGNED_MESSAGE, NOT_A_COORDINATOR_MESSAGE } from '@/mocks/handlers/lead'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-96 AC1 and SCRUM-24 AC3 (every active event with its status and coordinator), AC3 (each
 * coordinator's workload) and AC4 (only the Lead reassigns), as the Lead's oversight page shows
 * them (docs/adr/0062).
 */

const ACTIVE_URL = '/api/events/requests/active'
const WORKLOAD_URL = '/api/events/coordinators/workload'

const LEAD = mockSessionFor(MOCK_ACCOUNTS.lead)
const AISHA = MOCK_ACCOUNTS.otherCoordinator
const CHLOE = MOCK_ACCOUNTS.coordinator

/** A listed event with the fields every list shows; `name` and `reference` tell rows apart. */
function listedEvent(reference: string, name: string, status = 'approved') {
  return {
    reference,
    name,
    proposed_date: '2026-11-03',
    end_date: null,
    start_time: '08:15:00',
    end_time: '11:45:00',
    status,
  }
}

function renderOversight(session = LEAD) {
  return renderApp(ROUTES.LEAD_OVERSIGHT, { session })
}

async function findSection(name: string) {
  return within(await screen.findByRole('region', { name }))
}

/** One active event's card, found by its name inside the active events section. */
async function findActiveEvent(name: string) {
  const section = await findSection('Active events')
  return within(await section.findByRole('article', { name }))
}

/** One coordinator's card, found by their name inside the workload section. */
async function findWorkload(name: string) {
  const section = await findSection('Workload')
  return within(await section.findByRole('article', { name }))
}

/** The card headings in a section, top to bottom: coordinators' names or events' names. */
function cardNamesIn(sectionName: string) {
  const section = screen.getByRole('region', { name: sectionName })
  return within(section)
    .getAllByRole('heading', { level: 3 })
    .map((heading) => heading.textContent)
}

describe('SCRUM-96 the Lead oversight page: the workload', () => {
  it('lists each coordinator in the backend’s order, with their events’ names, dates and statuses', async () => {
    server.use(
      http.get(WORKLOAD_URL, () =>
        HttpResponse.json({
          coordinators: [
            {
              coordinator: 'Zara Lee',
              event_requests: [
                listedEvent('EVR-ZZ000002', 'Late Booking', 'under_review'),
                listedEvent('EVR-ZZ000001', 'Early Booking', 'confirmed'),
              ],
            },
            {
              coordinator: 'Adam Tan',
              event_requests: [listedEvent('EVR-AA000001', 'Adam’s Gig')],
            },
          ],
        }),
      ),
    )
    renderOversight()

    const zara = await findWorkload('Zara Lee')
    expect(cardNamesIn('Workload')).toEqual(['Zara Lee', 'Adam Tan'])
    const rows = zara.getAllByRole('listitem')
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining('Late Booking'),
      expect.stringContaining('Early Booking'),
    ])
    expect(within(rows[0] as HTMLElement).getByText('Under review')).toBeInTheDocument()
    expect(
      within(rows[0] as HTMLElement).getByText('3 Nov 2026 · 8:15 am – 11:45 am'),
    ).toBeInTheDocument()
    expect(within(rows[1] as HTMLElement).getByText('Confirmed')).toBeInTheDocument()
  })

  it('says a coordinator the backend lists with no events has none', async () => {
    server.use(
      http.get(WORKLOAD_URL, () =>
        HttpResponse.json({ coordinators: [{ coordinator: 'Idle Ian', event_requests: [] }] }),
      ),
    )
    renderOversight()

    const ian = await findWorkload('Idle Ian')
    expect(ian.getByText('No active events.')).toBeInTheDocument()
    expect(ian.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('shows the backend’s message when no coordinator holds an active event', async () => {
    server.use(
      http.get(WORKLOAD_URL, () =>
        HttpResponse.json({ coordinators: [], message: 'Nobody is carrying work right now.' }),
      ),
    )
    renderOversight()

    const workload = await findSection('Workload')
    expect(await workload.findByText('Nobody is carrying work right now.')).toBeInTheDocument()
    expect(workload.queryByRole('article')).not.toBeInTheDocument()
  })

  it('says it is loading the workload, then shows the backend’s error with a retry', async () => {
    server.use(
      http.get(
        WORKLOAD_URL,
        () =>
          HttpResponse.json(
            { error: 'server_error', message: 'The workload could not be read.' },
            { status: 500 },
          ),
        { once: true },
      ),
    )
    const { user } = renderOversight()

    const workload = await findSection('Workload')
    expect(workload.getByRole('status')).toHaveTextContent('Loading the workload…')
    expect(await workload.findByRole('alert')).toHaveTextContent('The workload could not be read.')
    await user.click(workload.getByRole('button', { name: 'Try again' }))
    expect(await workload.findByRole('article', { name: AISHA.full_name })).toBeInTheDocument()
  })
})

describe('SCRUM-96 the Lead oversight page: the active events', () => {
  it('shows each active event in the backend’s order with its date, time, status and coordinator', async () => {
    renderOversight()

    const active = await findSection('Active events')
    await active.findByRole('article', { name: 'Customer Insights Forum' })
    expect(cardNamesIn('Active events')).toEqual([
      'Customer Insights Forum',
      'Product Launch Evening',
      'Annual Partner Summit',
      'Founders’ Fireside Chat',
      'Quarterly Town Hall',
      'Harbourfront Gala Dinner',
      'Year-End Volunteer Fair',
    ])
    const gala = await findActiveEvent('Harbourfront Gala Dinner')
    expect(gala.getByText('EVR-LEAD0003')).toBeInTheDocument()
    expect(gala.getByText('5 Dec 2026')).toBeInTheDocument()
    expect(gala.getByText('7:00 pm – 11:00 pm')).toBeInTheDocument()
    expect(gala.getByText('Approved')).toBeInTheDocument()
    expect(gala.getByText(CHLOE.full_name)).toBeInTheDocument()
  })

  it('shows both days of an event that ends on a later day', async () => {
    renderOversight()

    const fair = await findActiveEvent('Year-End Volunteer Fair')
    expect(fair.getByText('14 Dec 2026 – 15 Dec 2026')).toBeInTheDocument()
  })

  it('offers a request nobody holds to the queue instead of a reassign form', async () => {
    renderOversight()

    const summit = await findActiveEvent('Annual Partner Summit')
    expect(summit.getByText('Not assigned')).toBeInTheDocument()
    expect(summit.getByRole('link', { name: 'Assign from the queue' })).toHaveAttribute(
      'href',
      ROUTES.LEAD_QUEUE,
    )
    expect(summit.queryByRole('textbox')).not.toBeInTheDocument()
    expect(summit.queryByRole('button')).not.toBeInTheDocument()
  })

  it('never links an event to its record, which the backend refuses the Lead', async () => {
    renderOversight()

    await findActiveEvent('Harbourfront Gala Dinner')
    const hrefs = screen.getAllByRole('link').map((link) => link.getAttribute('href'))
    expect(hrefs.some((href) => href?.startsWith('/events/'))).toBe(false)
  })

  it('shows the backend’s message when no event is active', async () => {
    server.use(
      http.get(ACTIVE_URL, () =>
        HttpResponse.json({ event_requests: [], message: 'Nothing is on the go at the moment.' }),
      ),
    )
    renderOversight()

    const active = await findSection('Active events')
    expect(await active.findByText('Nothing is on the go at the moment.')).toBeInTheDocument()
    expect(active.queryByRole('article')).not.toBeInTheDocument()
  })

  it('says it is loading the active events, then shows the backend’s error', async () => {
    server.use(
      http.get(ACTIVE_URL, () =>
        HttpResponse.json(
          { error: 'server_error', message: 'The active events could not be read.' },
          { status: 500 },
        ),
      ),
    )
    renderOversight()

    const active = await findSection('Active events')
    expect(active.getByRole('status')).toHaveTextContent('Loading active events…')
    expect(await active.findByRole('alert')).toHaveTextContent(
      'The active events could not be read.',
    )
  })
})

describe('SCRUM-96 the Lead oversight page: reassigning an event', () => {
  it('moves the event to the coordinator named by email, as the backend re-reads it', async () => {
    const requests = recordRequests()
    const { user } = renderOversight()
    const gala = await findActiveEvent('Harbourfront Gala Dinner')
    const field = gala.getByLabelText('Coordinator email for Harbourfront Gala Dinner')

    await user.type(field, AISHA.email)
    await user.click(gala.getByRole('button', { name: 'Reassign Harbourfront Gala Dinner' }))

    await waitFor(() => expect(gala.getByText(AISHA.full_name)).toBeInTheDocument())
    expect(gala.queryByText(CHLOE.full_name)).not.toBeInTheDocument()
    expect(field).toHaveValue('')
    const aisha = await findWorkload(AISHA.full_name)
    await waitFor(() => expect(aisha.getByText('Harbourfront Gala Dinner')).toBeInTheDocument())
    const post = requests.find((request) => request.method === 'POST')
    expect(new URL(post?.url ?? '').pathname).toBe('/api/events/requests/EVR-LEAD0003/reassign')
    expect(await post?.json()).toEqual({ coordinator_email: AISHA.email })
  })

  it('shows the backend’s message under the email when no coordinator has that address', async () => {
    const { user } = renderOversight()
    const gala = await findActiveEvent('Harbourfront Gala Dinner')
    const field = gala.getByLabelText('Coordinator email for Harbourfront Gala Dinner')

    await user.type(field, 'nobody@example.com')
    await user.click(gala.getByRole('button', { name: 'Reassign Harbourfront Gala Dinner' }))

    await waitFor(() => expect(field).toHaveAccessibleDescription(NOT_A_COORDINATOR_MESSAGE))
    expect(field).toBeInvalid()
    expect(field).toHaveValue('nobody@example.com')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(gala.getByText(CHLOE.full_name)).toBeInTheDocument()
  })

  it('shows the backend’s message in an alert when it refuses for another reason', async () => {
    const { user } = renderOversight()
    const gala = await findActiveEvent('Harbourfront Gala Dinner')

    await user.type(
      gala.getByLabelText('Coordinator email for Harbourfront Gala Dinner'),
      CHLOE.email,
    )
    await user.click(gala.getByRole('button', { name: 'Reassign Harbourfront Gala Dinner' }))

    expect(await gala.findByRole('alert')).toHaveTextContent(ALREADY_ASSIGNED_MESSAGE)
    const town = await findActiveEvent('Quarterly Town Hall')
    expect(town.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('SCRUM-96 the Lead oversight page: who sees it and how to reach it', () => {
  it('links the Lead between the queue and the oversight page', async () => {
    const { user, router } = renderApp(ROUTES.LEAD_QUEUE, { session: LEAD })

    const nav = within(await screen.findByRole('navigation', { name: 'Lead' }))
    expect(nav.getByRole('link', { name: 'Unassigned queue' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    await user.click(nav.getByRole('link', { name: 'Oversight' }))

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.LEAD_OVERSIGHT))
    const after = within(screen.getByRole('navigation', { name: 'Lead' }))
    expect(after.getByRole('link', { name: 'Oversight' })).toHaveAttribute('aria-current', 'page')
    expect(after.getByRole('link', { name: 'Unassigned queue' })).toHaveAttribute(
      'href',
      ROUTES.LEAD_QUEUE,
    )
  })

  it('sends an Event Coordinator to staff home without asking for either list (AC4)', async () => {
    const requests = recordRequests()
    const { router } = renderOversight(mockSessionFor(CHLOE))

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.STAFF_HOME))
    expect(screen.queryByRole('button', { name: /^Reassign/ })).not.toBeInTheDocument()
    const paths = requests.map((request) => new URL(request.url).pathname)
    expect(paths).not.toContain(ACTIVE_URL)
    expect(paths).not.toContain(WORKLOAD_URL)
  })

  it('sends a visitor who is signed out to the staff log-in page', async () => {
    const { router } = renderApp(ROUTES.LEAD_OVERSIGHT)

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN))
  })
})
