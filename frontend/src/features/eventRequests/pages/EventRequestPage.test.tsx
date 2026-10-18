import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { coordinatorEventPath, organiserRequestPath, ROUTES } from '@/config/routes'
import { fetchEventRequest } from '@/features/eventRequests/api'
import { MOCK_ACCOUNTS, mockSessionFor, mockTokenFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'
import { sendRequestsAs } from '@/test/sendRequestsAs'

/**
 * SCRUM-24 AC9, AC10: opening an event shows its record, with the sections the backend sends,
 * to an organiser of its organisation or to its assigned coordinator (ADR-0056). The records
 * come from the mock in src/mocks/handlers/eventRequests.ts: Chloe coordinates EVR-7K2M9QXA
 * "Partner Summit" and EVR-B6YF2K8V "Customer Roadshow"; Marcus decided EVR-W9CR5E7M and
 * EVR-M1XJ7T3D; EVR-Q4ZT6N1B has no coordinator; EVR-N5QS3V9C is another organisation's.
 */

const ORGANISER = mockSessionFor(MOCK_ACCOUNTS.organiser)
const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
const NOT_FOUND_MESSAGE = 'Event request not found.'

function openAsOrganiser(reference: string) {
  return renderApp(organiserRequestPath(reference), { session: ORGANISER })
}

function openAsCoordinator(reference: string) {
  return renderApp(coordinatorEventPath(reference), { session: COORDINATOR })
}

/** The section headed `name`, once the record has loaded. */
async function section(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { level: 2, name })
  const found = heading.closest('section')
  if (found === null) {
    throw new Error(`No section is headed "${name}"`)
  }
  return found
}

/** What the record says against `label` in the "About the event" list. */
async function detail(label: string): Promise<string | null> {
  const about = await section('About the event')
  const term = within(about).getByText(label, { selector: 'dt' })
  return term.nextElementSibling?.textContent ?? null
}

describe('SCRUM-24 AC9 event record: what an organiser sees', () => {
  it('heads the page with the event, its status, reference and when it is on', async () => {
    openAsOrganiser('EVR-7K2M9QXA')

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Partner Summit' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Under review')).toBeInTheDocument()
    expect(screen.getByText('EVR-7K2M9QXA')).toBeInTheDocument()
    expect(screen.getByText('Thu, 12 Nov · 9:00 am – 5:00 pm')).toBeInTheDocument()
  })

  it('lists the details the request has, and leaves out the ones it does not', async () => {
    openAsOrganiser('EVR-7K2M9QXA')

    expect(await detail('Purpose')).toBe('Meet our channel partners and plan next year together.')
    expect(await detail('Venue requirements')).toBe('A main hall for 250 and four breakout rooms.')
    expect(await detail('Expected attendance')).toBe('250')
    expect(await detail('Registration')).toBe('Not needed')
    const about = await section('About the event')
    expect(within(about).queryByText('Accessibility needs')).not.toBeInTheDocument()
  })

  it('leaves out the attendance of a draft that has none yet', async () => {
    openAsOrganiser('EVR-3HD8PL2W')

    const about = await section('About the event')
    expect(within(about).queryByText('Expected attendance')).not.toBeInTheDocument()
    expect(await detail('Registration')).toBe('Not needed')
  })

  it("shows the assigned coordinator's name and how to email them", async () => {
    openAsOrganiser('EVR-7K2M9QXA')

    const coordinator = await section('Coordinator')
    expect(within(coordinator).getByText('Chloe Lim')).toBeInTheDocument()
    expect(
      within(coordinator).getByRole('link', { name: 'chloe@connectsphere.test' }),
    ).toHaveAttribute('href', 'mailto:chloe@connectsphere.test')
  })

  it('says when no coordinator is assigned yet', async () => {
    openAsOrganiser('EVR-Q4ZT6N1B')

    const coordinator = await section('Coordinator')
    expect(within(coordinator).getByText('No coordinator is assigned yet.')).toBeInTheDocument()
  })

  it("shows the coordinator's programme notes", async () => {
    openAsOrganiser('EVR-7K2M9QXA')

    const notes = await section('Programme notes')
    expect(
      within(notes).getByText('Keynote at 9:30, breakout rooms after lunch.'),
    ).toBeInTheDocument()
  })

  it('shows a rejection with its reason, who made it and when', async () => {
    openAsOrganiser('EVR-M1XJ7T3D')

    const decision = await section('Decision')
    expect(within(decision).getByText('Rejected')).toBeInTheDocument()
    expect(
      within(decision).getByText('The proposed date clashes with the venue refurbishment.'),
    ).toBeInTheDocument()
    expect(
      within(decision).getByText('Decided by Marcus Tan, 29 Sept, 3:20 pm'),
    ).toBeInTheDocument()
  })

  it('shows an approval given without a reason', async () => {
    openAsOrganiser('EVR-W9CR5E7M')

    const decision = await section('Decision')
    expect(within(decision).getByText('Approved')).toBeInTheDocument()
    expect(
      within(decision).getByText('Decided by Marcus Tan, 30 Sept, 11:00 am'),
    ).toBeInTheDocument()
  })

  it('shows each clarification question with its answer, and the open one as waiting', async () => {
    openAsOrganiser('EVR-B6YF2K8V')

    const clarifications = await section('Clarifications')
    const exchanges = within(clarifications).getAllByRole('listitem')
    expect(exchanges).toHaveLength(2)
    const [answered, open] = exchanges as [HTMLElement, HTMLElement]
    expect(answered).toHaveTextContent(
      'Will the roadshow need a loading bay for the demo vehicles?',
    )
    expect(answered).toHaveTextContent('Asked by Chloe Lim, 26 Sept, 10:00 am')
    expect(answered).toHaveTextContent('Yes, for two vans between 11am and noon.')
    expect(answered).toHaveTextContent('Answered by Omar Rahman, 26 Sept, 2:30 pm')
    expect(open).toHaveTextContent('Can the start move to 2pm so the vans can unload first?')
    expect(open).toHaveTextContent('Waiting for an answer.')
  })

  it('says only when, for a decision and an answer whose author is no longer known', async () => {
    // The backend sends no name for a removed user (events/services.py _actor_name).
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.organiser))
    const record = await fetchEventRequest('EVR-B6YF2K8V')
    const [answered] = record.clarifications
    server.use(
      http.get('/api/events/requests/EVR-B6YF2K8V', () =>
        HttpResponse.json({
          ...record,
          decision: {
            outcome: 'rejected',
            reason: null,
            decided_by: null,
            decided_at: '2026-09-29T15:20:00+08:00',
          },
          clarifications: [{ ...answered, requested_by: null, answered_by: null }],
        }),
      ),
    )
    openAsOrganiser('EVR-B6YF2K8V')

    const decision = await section('Decision')
    expect(within(decision).getByText('Decided 29 Sept, 3:20 pm')).toBeInTheDocument()
    const clarifications = await section('Clarifications')
    expect(clarifications).toHaveTextContent('Asked 26 Sept, 10:00 am')
    expect(clarifications).toHaveTextContent('Answered 26 Sept, 2:30 pm')
  })

  it('leaves out the sections the record has nothing for', async () => {
    openAsOrganiser('EVR-Q4ZT6N1B')

    await section('About the event')
    for (const name of ['Decision', 'Clarifications', 'Programme notes']) {
      expect(screen.queryByRole('heading', { level: 2, name })).not.toBeInTheDocument()
    }
  })

  it('gives an organiser no links to the staff pages', async () => {
    openAsOrganiser('EVR-7K2M9QXA')

    await section('About the event')
    expect(screen.queryByRole('link', { name: 'Venue requests' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Equipment' })).not.toBeInTheDocument()
  })

  it("shows the backend's not-found message for another organisation's request", async () => {
    openAsOrganiser('EVR-N5QS3V9C')

    expect(await screen.findByRole('alert')).toHaveTextContent(NOT_FOUND_MESSAGE)
  })

  it('says it is loading while the record is on its way', async () => {
    openAsOrganiser('EVR-7K2M9QXA')

    expect(screen.getByRole('status')).toHaveTextContent('Loading the event')
    expect(await section('About the event')).toBeInTheDocument()
  })
})

describe('SCRUM-24 AC9, AC10 event record: what a coordinator sees', () => {
  it('opens an event assigned to them, with links on to its venue requests and equipment', async () => {
    openAsCoordinator('EVR-BOOK0101')

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Harbourfront Careers Fair' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Venue requests' })).toHaveAttribute(
      'href',
      '/events/EVR-BOOK0101/venue-requests',
    )
    expect(screen.getByRole('link', { name: 'Equipment' })).toHaveAttribute(
      'href',
      '/events/EVR-BOOK0101/equipment',
    )
  })

  it('shows what the organiser asked for, registration included', async () => {
    openAsCoordinator('EVR-BOOK0101')

    expect(await detail('Accessibility needs')).toBe('Step-free access')
    expect(await detail('Registration')).toBe('Needed')
  })

  it("can't open another coordinator's event, even by its link (AC10)", async () => {
    openAsCoordinator('EVR-W9CR5E7M')

    expect(await screen.findByRole('alert')).toHaveTextContent(NOT_FOUND_MESSAGE)
    expect(screen.queryByRole('link', { name: 'Venue requests' })).not.toBeInTheDocument()
  })
})

describe('SCRUM-24 event record: who reaches which address', () => {
  it("sends an organiser who opens the coordinator's address to their own home", () => {
    const { router } = renderApp(coordinatorEventPath('EVR-7K2M9QXA'), { session: ORGANISER })

    expect(router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME)
  })

  it("sends a coordinator who opens the organiser's address to their own home", () => {
    const { router } = renderApp(organiserRequestPath('EVR-7K2M9QXA'), { session: COORDINATOR })

    expect(router.state.location.pathname).toBe(ROUTES.STAFF_HOME)
  })

  it("sends a signed-out visitor at the coordinator's address to the staff log-in", () => {
    const { router } = renderApp(coordinatorEventPath('EVR-7K2M9QXA'))

    expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN)
  })
})
