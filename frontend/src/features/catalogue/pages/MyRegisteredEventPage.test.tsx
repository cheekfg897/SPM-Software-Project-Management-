import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { loginPathReturningTo, myEventPath, ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor, mockTokenFor } from '@/mocks/fixtures/accounts'
import { MOCK_CATALOGUE_EVENTS } from '@/mocks/handlers/catalogueFixtures'
import { server } from '@/mocks/server'
import { accountsOfEveryRoleBut } from '@/mocks/handlers/test/eventRequestCalls'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { registerForEvent } from '../api'
import type { MyRegisteredEvent } from '../api'

/**
 * SCRUM-24 AC11: an Attendee opens an event they registered for (docs/adr/0109). The mock's
 * "now" is Monday 5 Oct 2026, midday. The mock attendee holds Startup Pitch Night (7 Oct, 7 pm,
 * no cut-off) and this morning's Sunrise Yoga, which has started; they registered for the Orchid
 * Show Opening Night, since completed, and the Harbour Lights Run, since cancelled. Data Viz
 * Meetup's cut-off passed at 9 this morning.
 */

const ATTENDEE = mockSessionFor(MOCK_ACCOUNTS.attendee)
const ORCHID_SHOW = 'EVR-MOCK0901'
const HARBOUR_RUN = 'EVR-MOCK0902'
const ROOFTOP_FILM = 'EVR-MOCK0903'
const BEING_REVIEWED =
  'This event’s arrangements are being reviewed and may change. You will be notified of any change.'
const MY_EVENT_API = '/api/events/registrations/:reference'

/** How each status reads on the page, as the status chip words it. */
const STATUS_LABELS: Record<EventRequestStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  under_review: 'Under review',
  awaiting_clarification: 'Awaiting clarification',
  approved: 'Approved',
  safety_review: 'Safety review',
  confirmed: 'Confirmed',
  completed: 'Completed',
  cancelled: 'Cancelled',
  rejected: 'Rejected',
}

function catalogueEvent(name: string) {
  const event = MOCK_CATALOGUE_EVENTS.find((candidate) => candidate.name === name)
  if (event === undefined) {
    throw new Error(`No catalogue event is called ${name}`)
  }
  return event
}

const PITCH_NIGHT = catalogueEvent('Startup Pitch Night')
const SUNRISE_YOGA = catalogueEvent('Sunrise Yoga on the Lawn')
const DATA_VIZ = catalogueEvent('Data Viz Meetup')

/** Startup Pitch Night as the backend sends it, with only what a test changes. */
function pitchNight(overrides: Partial<MyRegisteredEvent> = {}): MyRegisteredEvent {
  return {
    id: PITCH_NIGHT.id,
    reference: PITCH_NIGHT.reference,
    name: PITCH_NIGHT.name,
    description: PITCH_NIGHT.description,
    starts_at: PITCH_NIGHT.starts_at,
    ends_at: PITCH_NIGHT.ends_at,
    event_status: 'confirmed',
    venues: [{ name: 'The Projector, Golden Mile Tower', location: '100 Beach Road, Level 5' }],
    status: 'registered',
    registered_at: '2026-10-05T12:00:00+08:00',
    withdrawn_at: null,
    withdrawals_close_at: PITCH_NIGHT.starts_at,
    can_withdraw: true,
    is_being_reviewed: false,
    ...overrides,
  }
}

/** Open the attendee's event, and wait for its name to show. */
async function openAsAttendee(reference: string, name: string) {
  const rendered = renderApp(myEventPath(reference), { session: ATTENDEE })
  await screen.findByRole('heading', { level: 1, name })
  return rendered
}

/** Withdraw through the button and its confirmation, as SCRUM-53's action asks. */
async function withdrawThroughThePage(user: ReturnType<typeof renderApp>['user'], name: string) {
  await user.click(screen.getByRole('button', { name: `Withdraw from ${name}` }))
  await user.click(screen.getByRole('button', { name: 'Yes, withdraw' }))
}

/**
 * Open Sunrise Yoga as the backend sent it before the event started, then try to withdraw: by now
 * it has started, so the backend refuses, saying when withdrawals closed.
 */
async function tryToWithdrawFromSunriseYogaAfterItStarted() {
  const sunriseYoga = {
    ...pitchNight(),
    id: SUNRISE_YOGA.id,
    reference: SUNRISE_YOGA.reference,
    name: SUNRISE_YOGA.name,
  }
  server.use(http.get(MY_EVENT_API, () => HttpResponse.json(sunriseYoga), { once: true }))
  const rendered = await openAsAttendee(SUNRISE_YOGA.reference, SUNRISE_YOGA.name)
  await withdrawThroughThePage(rendered.user, SUNRISE_YOGA.name)
  return rendered
}

/** The GETs of this event the page has sent so far. */
function readsOf(requests: Request[], reference: string): Request[] {
  return requests.filter(
    (request) =>
      request.method === 'GET' &&
      new URL(request.url).pathname === `/api/events/registrations/${reference}`,
  )
}

describe('SCRUM-24 my registered event page: what it shows', () => {
  it('shows that it is loading, then the event, its venue and the registration', async () => {
    renderApp(myEventPath(PITCH_NIGHT.reference), { session: ATTENDEE })

    expect(screen.getByRole('status')).toHaveTextContent('Loading the event…')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Startup Pitch Night' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByText('Wednesday 7 Oct, 7:00 pm – 9:30 pm')).toBeInTheDocument()
    expect(screen.getByText(PITCH_NIGHT.description)).toBeInTheDocument()
    expect(screen.getByText('Confirmed')).toBeInTheDocument()
    expect(screen.getByText('The Projector, Golden Mile Tower')).toBeInTheDocument()
    expect(screen.getByText('100 Beach Road, Level 5')).toBeInTheDocument()
    expect(screen.getByText('Registered')).toBeInTheDocument()
    expect(screen.getByText('You registered on 5 Oct, 12:00 pm.')).toBeInTheDocument()
  })

  it('says an event sent back to planning is being reviewed, and still offers Withdraw (AC11, 26 Oct)', async () => {
    await openAsAttendee(ROOFTOP_FILM, 'Rooftop Film Night')

    expect(screen.getByText(BEING_REVIEWED)).toBeInTheDocument()
    expect(screen.getByText('Approved')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Withdraw from Rooftop Film Night' }),
    ).toBeInTheDocument()
  })

  it('says nothing about a review for an event going ahead as planned', async () => {
    await openAsAttendee(PITCH_NIGHT.reference, PITCH_NIGHT.name)

    expect(screen.queryByText(BEING_REVIEWED)).not.toBeInTheDocument()
  })

  it('says when no venue is booked, as for a cancelled event', async () => {
    await openAsAttendee(HARBOUR_RUN, 'Harbour Lights Run')

    expect(screen.getByText('No venue is booked for this event.')).toBeInTheDocument()
  })

  it('shows the backend’s refusal for an event the attendee never registered for', async () => {
    renderApp(myEventPath(PITCH_NIGHT.reference), {
      session: mockSessionFor(MOCK_ACCOUNTS.freshAttendee),
    })

    expect(await screen.findByRole('alert')).toHaveTextContent('Event not found.')
    expect(screen.getByRole('heading', { level: 1, name: 'Your event' })).toBeInTheDocument()
  })

  it('is where the event link in the attendee’s notification opens (SCRUM-28)', async () => {
    // The backend's link is /events/<reference> (notifications/schemas.py, EVENT_LINK_TEMPLATE).
    server.use(
      http.get('/api/notifications', () =>
        HttpResponse.json({
          notifications: [
            {
              id: 1,
              kind: 'event_confirmed',
              message: 'Your event has been confirmed.',
              event_reference: PITCH_NIGHT.reference,
              event_name: PITCH_NIGHT.name,
              link: `/events/${PITCH_NIGHT.reference}`,
              created_at: '2026-10-05T09:00:00+08:00',
              read_at: null,
              detail: null,
            },
          ],
        }),
      ),
    )
    const { user, router } = renderApp(ROUTES.NOTIFICATIONS, { session: ATTENDEE })

    await user.click(await screen.findByRole('link', { name: PITCH_NIGHT.name }))

    expect(router.state.location.pathname).toBe(myEventPath(PITCH_NIGHT.reference))
    expect(
      await screen.findByRole('heading', { level: 1, name: PITCH_NIGHT.name }),
    ).toBeInTheDocument()
  })

  it('links back to My events', async () => {
    const { user, router } = await openAsAttendee(PITCH_NIGHT.reference, PITCH_NIGHT.name)

    await user.click(screen.getByRole('link', { name: 'Back to My events' }))

    expect(router.state.location.pathname).toBe(ROUTES.MY_EVENTS)
  })
})

describe('SCRUM-24 my registered event page: every event status', () => {
  it.each(Object.values(EVENT_REQUEST_STATUS))(
    'opens a %s event showing its status, with Withdraw only when the backend offers it',
    async (status) => {
      server.use(
        http.get(MY_EVENT_API, () =>
          HttpResponse.json(pitchNight({ event_status: status, can_withdraw: false })),
        ),
      )

      await openAsAttendee(PITCH_NIGHT.reference, PITCH_NIGHT.name)

      expect(screen.getByText(STATUS_LABELS[status])).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Withdraw/ })).not.toBeInTheDocument()
    },
  )

  it.each([
    [ORCHID_SHOW, 'Orchid Show Opening Night', 'Completed'],
    [HARBOUR_RUN, 'Harbour Lights Run', 'Cancelled'],
  ])('opens %s, a %s event, read-only with its status', async (reference, name, label) => {
    await openAsAttendee(reference, name)

    expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.getByText('Registered')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Withdraw/ })).not.toBeInTheDocument()
  })
})

describe('SCRUM-24 my registered event page: withdrawing (SCRUM-53)', () => {
  it('offers Withdraw before the event starts, saying until when', async () => {
    await openAsAttendee(PITCH_NIGHT.reference, PITCH_NIGHT.name)

    expect(screen.getByText('You can withdraw until 7 Oct, 7:00 pm.')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Withdraw from Startup Pitch Night' }),
    ).toBeInTheDocument()
  })

  it('withdraws after the attendee confirms, then reads the event again and shows it', async () => {
    const requests = recordRequests()
    const { user } = await openAsAttendee(PITCH_NIGHT.reference, PITCH_NIGHT.name)

    await withdrawThroughThePage(user, PITCH_NIGHT.name)

    expect(await screen.findByText('Withdrawn')).toBeInTheDocument()
    expect(screen.getByText('You withdrew on 5 Oct, 12:00 pm.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Withdraw/ })).not.toBeInTheDocument()
    const withdrawal = requests.find((request) => request.method === 'DELETE')
    expect(new URL(withdrawal?.url ?? '').pathname).toBe(
      `/api/events/catalogue/${PITCH_NIGHT.id}/registrations`,
    )
    expect(readsOf(requests, PITCH_NIGHT.reference)).toHaveLength(2)
  })

  it('offers no Withdraw once the cut-off has passed', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.attendee))
    await registerForEvent(DATA_VIZ.id)

    await openAsAttendee(DATA_VIZ.reference, DATA_VIZ.name)

    expect(screen.getByText('Registered')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Withdraw/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/You can withdraw until/)).not.toBeInTheDocument()
  })

  it('shows the refusal and the cut-off when withdrawals closed while the page was open, and reads the event again', async () => {
    const requests = recordRequests()

    await tryToWithdrawFromSunriseYogaAfterItStarted()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Withdrawals for this event have closed.',
    )
    await waitFor(() => {
      expect(readsOf(requests, SUNRISE_YOGA.reference)).toHaveLength(2)
    })
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Withdraw/ })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('alert')).toHaveTextContent('Withdrawals for this event have closed.')
    expect(screen.getByText('The cut-off was 5 Oct, 7:00 am.')).toBeInTheDocument()
  })

  it('keeps one event’s refusal off the page of another event that offers no Withdraw', async () => {
    const { router } = await tryToWithdrawFromSunriseYogaAfterItStarted()
    await screen.findByRole('alert')

    await router.navigate(myEventPath(ORCHID_SHOW))

    await screen.findByRole('heading', { level: 1, name: 'Orchid Show Opening Night' })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/The cut-off was/)).not.toBeInTheDocument()
  })
})

describe('SCRUM-24 my registered event page: who opens it', () => {
  /** One account of every role but the two that have a page at this address, built from ROLE. */
  const OTHER_ROLE_ACCOUNTS = accountsOfEveryRoleBut(ROLE.ATTENDEE).filter(
    ([role]) => role !== ROLE.EVENT_COORDINATOR,
  )

  /**
   * Where each role opens its own view of the event, written out rather than built from the path
   * helpers, so a wrong mapping shows. A notification's event link brings every role to this
   * address (SCRUM-28 AC1), so each must land on the event, not on its home. The Attendee and the
   * coordinator open theirs here.
   */
  const OWN_VIEW_OF_PITCH_NIGHT: Record<Role, string> = {
    [ROLE.ATTENDEE]: `/events/${PITCH_NIGHT.reference}`,
    [ROLE.EVENT_COORDINATOR]: `/events/${PITCH_NIGHT.reference}`,
    [ROLE.EVENT_ORGANISER]: `/organiser/requests/${PITCH_NIGHT.reference}`,
    [ROLE.EVENT_COORDINATOR_LEAD]: `/staff/events/${PITCH_NIGHT.reference}`,
    [ROLE.VENUE_STAFF]: `/staff/events/${PITCH_NIGHT.reference}`,
    [ROLE.TECHNICAL_SUPPORT_STAFF]: `/staff/events/${PITCH_NIGHT.reference}`,
    [ROLE.SAFETY_OFFICER]: `/staff/events/${PITCH_NIGHT.reference}`,
  }

  it.each(OTHER_ROLE_ACCOUNTS)(
    'takes the %s role to its own view of the event, without asking for the attendee’s',
    async (role, account) => {
      const requests = recordRequests()
      const { router } = renderApp(myEventPath(PITCH_NIGHT.reference), {
        session: mockSessionFor(account),
      })

      await waitFor(() => {
        expect(router.state.location.pathname).toBe(OWN_VIEW_OF_PITCH_NIGHT[role])
      })
      expect(readsOf(requests, PITCH_NIGHT.reference)).toEqual([])
    },
  )

  it('shows the coordinator their own record at this address, not the attendee’s page', async () => {
    const requests = recordRequests()
    renderApp(myEventPath(PITCH_NIGHT.reference), {
      session: mockSessionFor(MOCK_ACCOUNTS.coordinator),
    })

    await waitFor(() => {
      expect(
        requests.some(
          (request) =>
            new URL(request.url).pathname === `/api/events/requests/${PITCH_NIGHT.reference}`,
        ),
      ).toBe(true)
    })
    expect(readsOf(requests, PITCH_NIGHT.reference)).toEqual([])
  })

  it('sends a visitor to log in, and back here afterwards', async () => {
    const { router } = renderApp(myEventPath(PITCH_NIGHT.reference))

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN)
    })
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe(
      loginPathReturningTo(myEventPath(PITCH_NIGHT.reference), ROUTES.STAFF_LOGIN),
    )
  })

  it('leaves out no role: the two with a page here and the others are every role', () => {
    const otherRoles = OTHER_ROLE_ACCOUNTS.map(([role]) => role)
    expect(new Set([...otherRoles, ROLE.ATTENDEE, ROLE.EVENT_COORDINATOR])).toEqual(
      new Set(Object.values(ROLE)),
    )
  })
})
