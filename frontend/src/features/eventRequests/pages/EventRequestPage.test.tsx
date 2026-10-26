import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { coordinatorEventPath, organiserRequestPath, ROUTES } from '@/config/routes'
import { editEventRequest, fetchEventRequest } from '@/features/eventRequests/api'
import type { EventRecord, RecordVenueArrangement } from '@/features/eventRequests/api'
import { MOCK_ACCOUNTS, mockSessionFor, mockTokenFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { signedIn } from '@/store'
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
/** An arrangement as the organiser's record sends it in full, before its own details. */
const ARRANGEMENT_IN_FULL: RecordVenueArrangement = {
  venue_name: 'Orchid Room',
  venue_location: 'Marina Bay, Level 3',
  venue_capacity: 300,
  venue_facilities: ['stage', 'pa system'],
  venue_accessibility_features: [],
  starts_at: '2026-11-12T09:00:00+08:00',
  ends_at: '2026-11-12T12:00:00+08:00',
  purpose: 'Keynote',
  expected_occupancy: 250,
  required_layout: 'theatre',
  justification: null,
  status: 'approved',
  decision_reason: null,
  hold_expires_at: null,
  needs_alternative_venue: false,
  unavailability: [],
  flagged_after_change: false,
  reassessment_flags: [],
  preparation_status: 'not_started',
  preparation_notes: null,
}
/**
 * The Partner Summit's record with one of everything the organiser is sent on it (ADR-0104): a
 * held, an expired and a flagged arrangement, a reviewed line and the Safety Officer's outcome.
 */
const EVERYTHING_RECORDED: EventRecord = {
  reference: 'EVR-7K2M9QXA',
  status: 'approved',
  name: 'Partner Summit',
  purpose: null,
  description: null,
  proposed_date: '2026-11-12',
  end_date: '2026-11-12',
  start_time: '09:00:00',
  end_time: '17:00:00',
  expected_attendance: 250,
  venue_requirements: null,
  accessibility_needs: null,
  equipment_requirements: null,
  registration_required: false,
  created_at: '2026-10-01T09:00:00+08:00',
  programme_notes: null,
  coordinator: null,
  decision: null,
  clarifications: [],
  equipment_lines: [
    {
      equipment_type_name: 'Projector',
      quantity: 10,
      notes: 'Two at the back of the hall.',
      status: 'partially_fulfilled',
      provided_quantity: 6,
      shortfall: 4,
      outcome_note: 'Four are out for repair.',
      reviewed_by: 'Tariq Hassan',
      reviewed_at: '2026-10-05T11:00:00+08:00',
    },
  ],
  internal_planning_notes: 'Caterer arrives at 7:00.',
  venue_arrangements: [
    {
      ...ARRANGEMENT_IN_FULL,
      status: 'on_hold',
      hold_expires_at: '2026-10-30T17:00:00+08:00',
      justification: 'Only hall free that week.',
    },
    {
      ...ARRANGEMENT_IN_FULL,
      starts_at: '2026-11-12T13:00:00+08:00',
      ends_at: '2026-11-12T14:00:00+08:00',
      status: 'expired',
      hold_expires_at: '2026-10-25T17:00:00+08:00',
    },
    {
      ...ARRANGEMENT_IN_FULL,
      starts_at: '2026-11-12T15:00:00+08:00',
      ends_at: '2026-11-12T16:00:00+08:00',
      needs_alternative_venue: true,
      unavailability: [
        {
          category: 'maintenance',
          reason: 'Aircon repair',
          starts_at: '2026-11-01T08:00:00+08:00',
          ends_at: null,
        },
      ],
      flagged_after_change: true,
      reassessment_flags: [{ kind: 'requires_reconfirmation', reason: 'The date changed.' }],
    },
  ],
  equipment_reservations: [],
  safety_outcome: {
    outcome: 'approved',
    checklist: {
      attendance_vs_capacity: '250 expected in a hall for 300.',
      venue_layout: 'Theatre layout with two aisles.',
      emergency_access: 'Both fire exits are clear.',
      accessibility: 'Ramp at the side entrance.',
      equipment_placement: 'Cables taped down along the stage.',
      crowd_movement: 'One-way flow at the doors.',
      venue_restrictions: 'No open flames.',
    },
    reason: 'Keep the aisles clear.',
    recorded_by: 'Sana Iyer',
    recorded_at: '2026-10-04T14:00:00+08:00',
  },
}

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

describe('SCRUM-24 AC10 event record: everything an organiser sees, at every stage', () => {
  const SARA = mockSessionFor(MOCK_ACCOUNTS.otherOrganiser)
  /** Every status a submitted event can be in, built from the enum: all but a draft. */
  const SUBMITTED_STATUSES = Object.values(EVENT_REQUEST_STATUS).filter(
    (status) => status !== EVENT_REQUEST_STATUS.DRAFT,
  )

  /** Answer the organiser's record with everything on it, in `status`, whatever is asked for. */
  function recordWithEverything(status: EventRequestStatus) {
    server.use(
      http.get('/api/events/requests/:reference', () =>
        HttpResponse.json({ ...EVERYTHING_RECORDED, status }),
      ),
    )
  }

  it.each(SUBMITTED_STATUSES)(
    'shows every section of the record while the event is %s',
    async (status) => {
      recordWithEverything(status)
      openAsOrganiser('EVR-7K2M9QXA')

      expect(await section('Planning notes')).toHaveTextContent('Caterer arrives at 7:00.')
      expect(await section('Venue arrangements')).toHaveTextContent('Orchid Room')
      expect(await section('Equipment')).toHaveTextContent(
        'Reviewed by Tariq Hassan, 5 Oct, 11:00 am',
      )
      expect(await section('Safety check')).toHaveTextContent('Keep the aisles clear.')
    },
  )

  it("shows every arrangement with its status, where it is, what was asked for and Venue Staff's reason", async () => {
    renderApp(organiserRequestPath('EVR-BOOK0112'), { session: SARA })

    const venues = await section('Venue arrangements')
    const [reception, dinner, overflow] = within(venues).getAllByRole('listitem') as [
      HTMLElement,
      HTMLElement,
      HTMLElement,
    ]
    expect(dinner).toHaveTextContent('Marina Hall')
    expect(dinner).toHaveTextContent('Level 1, Marina Wing')
    expect(dinner).toHaveTextContent('5 Dec, 6:00 pm – 11:00 pm · Approved')
    expect(dinner).toHaveTextContent('Gala dinner · 10 guests · Banquet')
    expect(dinner).toHaveTextContent(
      'Holds 200 · Facilities: projector, stage · Accessibility: step-free access, hearing loop',
    )
    expect(dinner).toHaveTextContent('Venue Staff: Booked for the dinner.')
    expect(dinner).toHaveTextContent('Tables set for 80.')
    expect(reception).toHaveTextContent('Drinks reception · 10 guests · No layout set')
    expect(overflow).toHaveTextContent('5 Dec, 7:00 pm – 9:00 pm · Withdrawn')
  })

  it("shows a hold's expiry, a hold that expired, and each flag with its reason", async () => {
    recordWithEverything(EVENT_REQUEST_STATUS.APPROVED)
    openAsOrganiser('EVR-7K2M9QXA')

    const venues = await section('Venue arrangements')
    // The flagged arrangement's reasons are list items too, after the three arrangements.
    const [held, expired, flagged] = within(venues).getAllByRole('listitem') as [
      HTMLElement,
      HTMLElement,
      HTMLElement,
    ]
    expect(held).toHaveTextContent('Hold expires 30 Oct, 5:00 pm')
    // A venue with no accessibility features listed says so (SCRUM-24 AC10, 26 Oct).
    expect(held).toHaveTextContent(
      'Holds 300 · Facilities: stage, pa system · Accessibility: none listed',
    )
    expect(held).toHaveTextContent('Why this venue: Only hall free that week.')
    expect(expired).toHaveTextContent('Hold expired 25 Oct, 5:00 pm')
    expect(
      within(flagged).getByRole('list', { name: 'Needs an alternative venue' }),
    ).toHaveTextContent(
      'Maintenance: Aircon repair. Unavailable from 1 Nov, 8:00 am until the venue is reactivated.',
    )
    expect(
      within(flagged).getByRole('list', { name: 'Flagged after a change to the event' }),
    ).toHaveTextContent('Requires reconfirmation: The date changed.')
  })

  it("shows each line's technical notes, outcome, outcome note and who reviewed it", async () => {
    openAsOrganiser('EVR-7K2M9QXA')

    const requested = within(await section('Equipment')).getByRole('list', {
      name: 'Equipment requested',
    })
    const [projectors, microphones, lectern] = within(requested).getAllByRole('listitem') as [
      HTMLElement,
      HTMLElement,
      HTMLElement,
    ]
    expect(projectors).toHaveTextContent('Projector · 10 requested')
    expect(projectors).toHaveTextContent('Note: Two at the back of the hall.')
    // The shortfall is drawn when there is one (SCRUM-24 AC10, 26 Oct), never when it is 0.
    expect(projectors).toHaveTextContent(
      'Technical Support: Partially fulfilled, 6 provided, 4 short',
    )
    expect(lectern).toHaveTextContent('Technical Support: Fulfilled, 1 provided')
    expect(lectern).not.toHaveTextContent('short')
    expect(projectors).toHaveTextContent('Four are out for repair.')
    expect(projectors).toHaveTextContent('Reviewed by Tariq Hassan, 5 Oct, 11:00 am')
    expect(microphones).toHaveTextContent('Technical Support: Awaiting Technical Support')
    expect(microphones).not.toHaveTextContent('Reviewed')
  })

  it('says when nothing is reserved yet, and when no planning notes are saved', async () => {
    openAsOrganiser('EVR-7K2M9QXA')

    expect(await section('Equipment')).toHaveTextContent(
      'No equipment is reserved for this event yet.',
    )
    expect(await section('Planning notes')).toHaveTextContent('No planning notes yet.')
  })

  it('shows the planning notes the coordinator saved (SCRUM-33 AC1)', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
    await editEventRequest('EVR-7K2M9QXA', { internal_planning_notes: 'Client prefers mornings.' })
    sendRequestsAs(null)
    openAsOrganiser('EVR-7K2M9QXA')

    expect(await section('Planning notes')).toHaveTextContent('Client prefers mornings.')
  })

  it("shows the Safety Officer's outcome with each checklist note, who recorded it and when", async () => {
    renderApp(organiserRequestPath('EVR-BOOK0102'), { session: SARA })

    const safety = await section('Safety check')
    expect(within(safety).getByText('Approved')).toBeInTheDocument()
    expect(within(safety).getByText('Both fire exits are clear.')).toBeInTheDocument()
    expect(within(safety).getByText('Recorded by Sana Iyer, 4 Oct, 2:00 pm')).toBeInTheDocument()
  })

  it('shows a request for changes and its reason before the event is confirmed', async () => {
    openAsOrganiser('EVR-W9CR5E7M')

    const safety = await section('Safety check')
    expect(within(safety).getByText('Changes requested')).toBeInTheDocument()
    expect(
      within(safety).getByText('Keep the terrace exit clear during the dinner.'),
    ).toBeInTheDocument()
  })

  it('shows none of these sections to the coordinator, who works on them from their own pages', async () => {
    openAsCoordinator('EVR-7K2M9QXA')

    await section('About the event')
    for (const name of ['Planning notes', 'Venue arrangements', 'Equipment', 'Safety check']) {
      expect(screen.queryByRole('heading', { level: 2, name })).not.toBeInTheDocument()
    }
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
    // Within the page: the header has an Equipment link too, to the catalogue (SCRUM-27).
    expect(
      within(screen.getByRole('main')).getByRole('link', { name: 'Equipment' }),
    ).toHaveAttribute('href', '/events/EVR-BOOK0101/equipment')
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

  it("reads the record again for the next coordinator to sign in, never showing the last one's", async () => {
    const { store } = openAsCoordinator('EVR-7K2M9QXA')
    await screen.findByRole('heading', { level: 1, name: 'Partner Summit' })

    store.dispatch(signedIn(mockSessionFor(MOCK_ACCOUNTS.freshCoordinator)))

    expect(await screen.findByRole('alert')).toHaveTextContent(NOT_FOUND_MESSAGE)
    expect(screen.queryByRole('heading', { name: 'Partner Summit' })).not.toBeInTheDocument()
  })
})

describe('SCRUM-24 event record: who reaches which address', () => {
  it("takes an organiser who opens the coordinator's address, as a notification links, to their own record", async () => {
    const { router } = renderApp(coordinatorEventPath('EVR-7K2M9QXA'), { session: ORGANISER })

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Partner Summit' }),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/organiser/requests/EVR-7K2M9QXA')
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
