import { screen, waitFor, within } from '@testing-library/react'
import type { BoundFunctions, queries } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_FAIR, MOCK_GALA } from '@/mocks/handlers/safetyFixtures'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-97 AC5, AC6 and SCRUM-24 AC6, AC8, AC11: the Safety Officer's list of events awaiting
 * the safety check. SCRUM-98 AC1-AC4: recording the outcome with its checklist and reason, and
 * seeing what happened (docs/adr/0071).
 */

const LIST_URL = '/api/events/requests/awaiting-safety-review'
const OFFICER = mockSessionFor(MOCK_ACCOUNTS.safetyOfficer)
const GALA = MOCK_GALA.event.name
const FAIR = MOCK_FAIR.event.name
const TOWN_HALL = 'Year-End Town Hall'
const OPEN_FORM = 'Record safety check'
const REASON_REQUIRED = 'A reason is required to reject the event or request changes.'

/** SCRUM-98 AC2's seven items, in its order and its words. */
const CHECKLIST_LABELS = [
  'Expected attendance versus venue capacity',
  'Venue layout',
  'Emergency access',
  'Accessibility requirements',
  'Equipment placement',
  'Crowd movement',
  'Known venue restrictions',
]
/** SCRUM-98 AC3: the items the system holds no data for. */
const NOT_HELD_ITEMS = [
  'Emergency access',
  'Equipment placement',
  'Crowd movement',
  'Known venue restrictions',
]
const NOT_HELD_HINT = 'ConnectSphere holds no data on this. Record your own assessment.'

/** The note typed into each item, so the body sent can be checked against it. */
function noteFor(label: string): string {
  return `Checked: ${label}.`
}

function renderList() {
  return renderApp(ROUTES.SAFETY_REVIEW, { session: OFFICER })
}

/** An event's card, found by the name its heading gives it. */
async function findEvent(name: string) {
  return within(await screen.findByRole('article', { name }))
}

/** Open an event's outcome form; the card it sits in is returned. */
async function openForm(user: UserEvent, name: string) {
  const card = await findEvent(name)
  await user.click(card.getByRole('button', { name: OPEN_FORM }))
  return card
}

async function fillChecklist(user: UserEvent, card: BoundFunctions<typeof queries>) {
  for (const label of CHECKLIST_LABELS) {
    await user.click(card.getByLabelText(label))
    await user.paste(noteFor(label))
  }
}

/** The checklist body the backend should get when every note was typed with `noteFor`. */
const SENT_CHECKLIST = {
  attendance_vs_capacity: noteFor('Expected attendance versus venue capacity'),
  venue_layout: noteFor('Venue layout'),
  emergency_access: noteFor('Emergency access'),
  accessibility: noteFor('Accessibility requirements'),
  equipment_placement: noteFor('Equipment placement'),
  crowd_movement: noteFor('Crowd movement'),
  venue_restrictions: noteFor('Known venue restrictions'),
}

function outcomePosts(requests: Request[]) {
  return requests.filter((request) => request.method === 'POST')
}

function listReads(requests: Request[]) {
  return requests.filter(
    (request) => request.method === 'GET' && new URL(request.url).pathname === LIST_URL,
  )
}

describe('SCRUM-97 and SCRUM-24 AC6 the Safety Officer list', () => {
  it('lists the events awaiting the safety check soonest first, in the order the backend sent', async () => {
    renderList()

    expect(screen.getByRole('status')).toHaveTextContent('Loading events awaiting the safety check')
    await findEvent(FAIR)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(
      screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent),
    ).toEqual([FAIR, TOWN_HALL, GALA])
  })

  it("shows each event's name, reference, date, time, status, attendance and accessibility needs", async () => {
    renderList()

    const gala = await findEvent(GALA)
    expect(gala.getByText('EVR-SAFE0002')).toBeInTheDocument()
    expect(gala.getByText('Fri, 4 Dec · 6:00 pm – 11:00 pm')).toBeInTheDocument()
    expect(gala.getByText('Safety review')).toBeInTheDocument()
    expect(gala.getByText('400')).toBeInTheDocument()
    expect(gala.getByText('Wheelchair seating for six guests')).toBeInTheDocument()
    const fair = await findEvent(FAIR)
    expect(fair.getByText('Sat, 21 Nov · 9:00 am – 4:00 pm')).toBeInTheDocument()
    expect(fair.getByText('250')).toBeInTheDocument()
    expect(fair.getByText('None given')).toBeInTheDocument()
  })

  it("shows each booked venue's capacity, layouts, facilities, accessibility features and booked period", async () => {
    renderList()

    const venue = within((await findEvent(GALA)).getByRole('listitem', { name: 'Marina Ballroom' }))
    expect(venue.getByText('4 Dec, 5:00 pm – 11:30 pm')).toBeInTheDocument()
    expect(venue.getByText('500')).toBeInTheDocument()
    expect(venue.getByText('Banquet, Theatre')).toBeInTheDocument()
    expect(venue.getByText('stage, pa system')).toBeInTheDocument()
    expect(venue.getByText('wheelchair access, hearing loop')).toBeInTheDocument()
    const fairVenue = within((await findEvent(FAIR)).getByRole('listitem', { name: 'Atrium Hall' }))
    expect(fairVenue.getByText('Exhibition')).toBeInTheDocument()
    expect(fairVenue.getAllByText('None listed')).toHaveLength(2)
  })

  it("shows each equipment request with its quantity, notes and Technical Support's outcome", async () => {
    renderList()

    const gala = await findEvent(GALA)
    const projector = within(gala.getByRole('listitem', { name: 'Projector' }))
    expect(projector.getByText('2 requested')).toBeInTheDocument()
    expect(projector.getByText('Ceiling mount')).toBeInTheDocument()
    expect(projector.getByText('Fulfilled, 2 provided')).toBeInTheDocument()
    const microphones = within(gala.getByRole('listitem', { name: 'Wireless microphone' }))
    expect(microphones.getByText('6 requested')).toBeInTheDocument()
    expect(microphones.getByText('Partially fulfilled, 4 provided')).toBeInTheDocument()
    expect(microphones.getByText('Only four in stock that week.')).toBeInTheDocument()
    const lectern = within((await findEvent(TOWN_HALL)).getByRole('listitem', { name: 'Lectern' }))
    expect(lectern.getByText('Unavailable, 0 provided')).toBeInTheDocument()
    expect((await findEvent(FAIR)).getByText('No equipment requested.')).toBeInTheDocument()
  })

  it('says so when an event has no venue booked', async () => {
    server.use(
      http.get(LIST_URL, () =>
        HttpResponse.json({ events: [{ event: MOCK_FAIR.event, venues: [], equipment: [] }] }),
      ),
    )
    renderList()

    expect((await findEvent(FAIR)).getByText('No venue booked.')).toBeInTheDocument()
  })

  it('shows a layout or an equipment request it has no words for as the backend sent it', async () => {
    const venue = { ...MOCK_FAIR.venues[0], layouts: ['amphitheatre'] }
    const equipment = {
      equipment_type_name: 'Stage riser',
      quantity: 3,
      notes: null,
      status: 'requested',
      provided_quantity: null,
      outcome_note: null,
    }
    server.use(
      http.get(LIST_URL, () =>
        HttpResponse.json({
          events: [{ event: MOCK_FAIR.event, venues: [venue], equipment: [equipment] }],
        }),
      ),
    )
    renderList()

    const fair = await findEvent(FAIR)
    expect(fair.getByText('amphitheatre')).toBeInTheDocument()
    expect(
      within(fair.getByRole('listitem', { name: 'Stage riser' })).getByText('Requested'),
    ).toBeInTheDocument()
  })

  it("shows the backend's message instead of a list when no event is waiting", async () => {
    server.use(
      http.get(LIST_URL, () =>
        HttpResponse.json({ events: [], message: 'Nothing for the Safety Officer today.' }),
      ),
    )
    renderList()

    expect(await screen.findByText('Nothing for the Safety Officer today.')).toBeInTheDocument()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it("shows the backend's message when the list cannot be read, and reads it again on Try again", async () => {
    server.use(
      http.get(
        LIST_URL,
        () =>
          HttpResponse.json(
            { error: 'server_error', message: 'Something went wrong.' },
            { status: 500 },
          ),
        { once: true },
      ),
    )
    const { user } = renderList()

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('article', { name: GALA })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ])('sends %s to the staff home without asking for the list', async (_who, account) => {
    const requests = recordRequests()
    const { router } = renderApp(ROUTES.SAFETY_REVIEW, { session: mockSessionFor(account) })

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.STAFF_HOME))
    expect(listReads(requests)).toHaveLength(0)
  })

  it('sends a visitor to the staff log-in page', async () => {
    const { router } = renderApp(ROUTES.SAFETY_REVIEW)

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN))
  })

  it('links the Safety Officer to the list from the header', () => {
    renderApp(ROUTES.EVENTS, { session: OFFICER })

    const header = within(screen.getByRole('banner'))
    expect(header.getByRole('link', { name: 'Safety review' })).toHaveAttribute(
      'href',
      ROUTES.SAFETY_REVIEW,
    )
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['an Attendee', MOCK_ACCOUNTS.attendee],
  ])('shows %s no link to the safety list', (_who, account) => {
    renderApp(ROUTES.EVENTS, { session: mockSessionFor(account) })

    expect(
      within(screen.getByRole('banner')).queryByRole('link', { name: 'Safety review' }),
    ).not.toBeInTheDocument()
  })
})

describe('SCRUM-98 recording the safety check outcome', () => {
  it('opens a form with the seven checklist items in the AC wording, and a reason', async () => {
    const { user } = renderList()
    const gala = await findEvent(GALA)
    const toggle = gala.getByRole('button', { name: OPEN_FORM })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(gala.queryByLabelText('Venue layout')).not.toBeInTheDocument()

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const form = within(gala.getByRole('form', { name: `Safety check for ${GALA}` }))
    expect(form.getAllByRole('textbox')).toHaveLength(8)
    for (const label of CHECKLIST_LABELS) {
      expect(form.getByLabelText(label)).toBeInTheDocument()
    }
    expect(form.getByLabelText('Reason')).toHaveAccessibleDescription(
      'Required to reject or request changes.',
    )
    for (const label of NOT_HELD_ITEMS) {
      expect(form.getByLabelText(label)).toHaveAccessibleDescription(NOT_HELD_HINT)
    }
    expect(form.getByLabelText('Venue layout')).not.toHaveAccessibleDescription()
    expect(form.getByRole('button', { name: `Approve ${GALA}` })).toBeInTheDocument()
    expect(form.getByRole('button', { name: `Reject ${GALA}` })).toBeInTheDocument()
    expect(form.getByRole('button', { name: `Request changes ${GALA}` })).toBeInTheDocument()
  })

  it('closes the form again', async () => {
    const { user } = renderList()
    const gala = await openForm(user, GALA)

    await user.click(gala.getByRole('button', { name: OPEN_FORM }))

    expect(gala.queryByRole('form')).not.toBeInTheDocument()
  })

  it.each([
    [
      'Approve',
      'approved',
      'Safety review',
      'It stays in Safety review until its coordinator confirms it.',
    ],
    [
      'Reject',
      'rejected',
      'Approved',
      'It goes back to its coordinator at Approved, the planning stage.',
    ],
    [
      'Request changes',
      'changes_requested',
      'Approved',
      'It goes back to its coordinator at Approved, the planning stage.',
    ],
  ])(
    '%s sends the outcome, notes and reason, then the event leaves the list and the page says what happened',
    async (action, outcome, statusAfter, nextStep) => {
      const requests = recordRequests()
      const { user } = renderList()
      const gala = await openForm(user, GALA)
      await fillChecklist(user, gala)
      await user.type(gala.getByLabelText('Reason'), 'Second exit is blocked.')

      await user.click(gala.getByRole('button', { name: `${action} ${GALA}` }))

      await waitFor(() =>
        expect(screen.queryByRole('article', { name: GALA })).not.toBeInTheDocument(),
      )
      const [post] = outcomePosts(requests)
      expect(new URL(post?.url ?? '').pathname).toBe(
        '/api/events/requests/EVR-SAFE0002/safety-outcome',
      )
      expect(await post?.json()).toEqual({
        outcome,
        checklist: SENT_CHECKLIST,
        reason: 'Second exit is blocked.',
      })
      expect(listReads(requests)).toHaveLength(2)
      const notice = within(screen.getByRole('status'))
      expect(notice.getByText(`Safety check recorded for ${GALA}: ${action}.`)).toBeInTheDocument()
      expect(notice.getByText(statusAfter)).toBeInTheDocument()
      expect(notice.getByText(nextStep)).toBeInTheDocument()
      expect(notice.getByText('Its coordinator has been notified.')).toBeInTheDocument()
      expect(screen.getByRole('article', { name: FAIR })).toBeInTheDocument()
    },
  )

  it('sends no reason with an approval when none was typed', async () => {
    const requests = recordRequests()
    const { user } = renderList()
    const gala = await openForm(user, GALA)
    await fillChecklist(user, gala)

    await user.click(gala.getByRole('button', { name: `Approve ${GALA}` }))

    await waitFor(() => expect(outcomePosts(requests)).toHaveLength(1))
    expect(await outcomePosts(requests)[0]?.json()).toEqual({
      outcome: 'approved',
      checklist: SENT_CHECKLIST,
    })
  })

  it("shows the backend's reason message under Reason, moves there, and keeps the event", async () => {
    const { user } = renderList()
    const gala = await openForm(user, GALA)
    await fillChecklist(user, gala)

    await user.click(gala.getByRole('button', { name: `Reject ${GALA}` }))

    const reason = gala.getByLabelText('Reason')
    await waitFor(() => expect(reason).toHaveAccessibleDescription(REASON_REQUIRED))
    expect(reason).toBeInvalid()
    expect(reason).toHaveFocus()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('article', { name: GALA })).toBeInTheDocument()
    expect(screen.queryByText(/^Safety check recorded/)).not.toBeInTheDocument()
  })

  it("shows the backend's message under every checklist note left blank, and moves to the first", async () => {
    const { user } = renderList()
    const gala = await openForm(user, GALA)
    await user.type(gala.getByLabelText('Venue layout'), '   ')

    await user.click(gala.getByRole('button', { name: `Approve ${GALA}` }))

    const first = gala.getByLabelText(CHECKLIST_LABELS[0] ?? '')
    await waitFor(() => expect(first).toHaveAccessibleDescription('Must not be blank.'))
    expect(first).toHaveFocus()
    for (const label of CHECKLIST_LABELS) {
      expect(gala.getByLabelText(label)).toHaveAccessibleDescription('Must not be blank.')
    }
    expect(gala.getByLabelText('Reason')).toBeValid()
  })

  it("shows the backend's message in an alert when it refuses the outcome, and keeps the event", async () => {
    server.use(
      http.post('/api/events/requests/:reference/safety-outcome', () =>
        HttpResponse.json(
          {
            error: 'safety_outcome_not_allowed',
            message: 'The Safety Officer has already approved this event.',
          },
          { status: 409 },
        ),
      ),
    )
    const { user } = renderList()
    const gala = await openForm(user, GALA)
    await fillChecklist(user, gala)

    await user.click(gala.getByRole('button', { name: `Approve ${GALA}` }))

    expect(await gala.findByRole('alert')).toHaveTextContent(
      'The Safety Officer has already approved this event.',
    )
    expect(screen.getByRole('article', { name: GALA })).toBeInTheDocument()
    expect(screen.queryByText(/^Safety check recorded/)).not.toBeInTheDocument()
  })

  it("keeps one event's refusal on that event's form only", async () => {
    const { user } = renderList()
    const gala = await openForm(user, GALA)
    const fair = await openForm(user, FAIR)
    await fillChecklist(user, gala)

    await user.click(gala.getByRole('button', { name: `Reject ${GALA}` }))

    await waitFor(() =>
      expect(gala.getByLabelText('Reason')).toHaveAccessibleDescription(REASON_REQUIRED),
    )
    expect(fair.getByLabelText('Reason')).toBeValid()
    expect(fair.getByRole('button', { name: `Reject ${FAIR}` })).toBeEnabled()
  })

  it('keeps saying what was recorded last once no event is left waiting', async () => {
    const { user } = renderList()
    for (const name of [FAIR, TOWN_HALL, GALA]) {
      const card = await openForm(user, name)
      await fillChecklist(user, card)
      await user.click(card.getByRole('button', { name: `Approve ${name}` }))
      await waitFor(() => expect(screen.queryByRole('article', { name })).not.toBeInTheDocument())
    }

    expect(
      await screen.findByText('No events are waiting for a safety review.'),
    ).toBeInTheDocument()
    expect(
      within(screen.getByRole('status')).getByText(`Safety check recorded for ${GALA}: Approve.`),
    ).toBeInTheDocument()
  })
})
