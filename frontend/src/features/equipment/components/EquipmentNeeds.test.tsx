import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { eventEquipmentPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import {
  MOCK_OPEN_EVENT_REFERENCE,
  mockStatusEventReference,
} from '@/mocks/handlers/equipmentFixtures'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-37 on the Equipment page: the assigned coordinator adds, changes and removes the event's
 * equipment lines (AC1, AC2), a quantity below 1 is refused in the backend's words (AC3), and
 * staff see each line and its status (AC5). ADR-0065.
 */

const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
const TECHNICAL_SUPPORT = mockSessionFor(MOCK_ACCOUNTS.technicalSupport)
const OPEN_PAGE = eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE)
const LINES_PATH = `/api/events/requests/${MOCK_OPEN_EVENT_REFERENCE}/equipment`
const PROJECTOR_NOTES = 'Ceiling-mounted, with HDMI at the lectern.'

type User = ReturnType<typeof renderApp>['user']

function linesTable() {
  return screen.getByRole('table', { name: 'Equipment lines' })
}

/** Each line's cells, in the order the table shows them. */
function lineRows(): string[][] {
  const rows = within(linesTable()).getAllByRole('row').slice(1)
  return rows.map((row) =>
    within(row)
      .getAllByRole('cell')
      .slice(0, 4)
      .map((cell) => cell.textContent ?? ''),
  )
}

/** The "Requested" figure the availability table shows for one equipment type. */
function requestedInAvailability(name: string): string | null | undefined {
  const table = screen.getByRole('table', { name: 'Equipment availability' })
  const row = within(table).getByRole('cell', { name }).closest('tr')
  return row?.querySelectorAll('td')[2]?.textContent
}

/** The JSON body of the last request sent with `method`. */
async function sentBody(requests: Request[], method: string): Promise<unknown> {
  const sent = requests.filter((request) => request.method === method).at(-1)
  return sent?.json()
}

async function openAsCoordinator(path = OPEN_PAGE) {
  const rendered = renderApp(path, { session: COORDINATOR })
  await screen.findByRole('heading', { name: 'What this event needs' })
  return rendered
}

async function addLine(user: User, values: { type?: string; quantity?: string; notes?: string }) {
  if (values.type !== undefined) {
    await user.selectOptions(screen.getByLabelText('Equipment type'), values.type)
  }
  if (values.quantity !== undefined) {
    await user.type(screen.getByLabelText('Quantity'), values.quantity)
  }
  if (values.notes !== undefined) {
    await user.type(screen.getByLabelText('Technical notes'), values.notes)
  }
  await user.click(screen.getByRole('button', { name: 'Add line' }))
}

/** The cells of the line whose equipment is `name`, in the order the table shows them. */
function cellsOf(name: string): HTMLTableCellElement[] {
  const row = within(linesTable()).getByRole('cell', { name }).closest('tr')
  return Array.from(row?.querySelectorAll('td') ?? [])
}

/** The Outcome cell of the line whose equipment is `name`. */
function outcomeCell(name: string): HTMLElement {
  const cell = cellsOf(name)[4]
  if (cell === undefined) {
    throw new Error(`No outcome cell for ${name}`)
  }
  return cell
}

/** The Status cell's words for the line whose equipment is `name`. */
function statusOf(name: string): string | null | undefined {
  return cellsOf(name)[3]?.textContent
}

/** Make the backend refuse every change or removal of a line with `message`. */
function refuseLineWith(method: 'patch' | 'delete', message: string) {
  server.use(
    http[method](`${LINES_PATH}/:lineId`, () =>
      HttpResponse.json({ error: 'equipment_not_editable', message }, { status: 409 }),
    ),
  )
}

describe('SCRUM-37 equipment page: what the event needs (AC5)', () => {
  it('lists each line by type name, in the order the backend sent, with its status in words', async () => {
    renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    await screen.findByRole('table', { name: 'Equipment lines' })
    expect(lineRows()).toEqual([
      ['Projector', '8', PROJECTOR_NOTES, 'Awaiting Technical Support'],
      ['Microphone', '4', 'No notes', 'Fulfilled'],
    ])
    expect(screen.getByText(/Annual Partner Summit/)).toBeInTheDocument()
  })

  it('comes before availability and reservations', async () => {
    renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    await screen.findByRole('table', { name: 'Equipment lines' })
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['What this event needs', 'Availability', 'Reserved for this event'])
  })

  it('gives Technical Support no way to change the lines', async () => {
    renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    await screen.findByRole('table', { name: 'Equipment lines' })
    expect(
      within(linesTable()).queryByRole('columnheader', { name: 'Change or remove' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Change|Remove|Add line/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Equipment type')).not.toBeInTheDocument()
  })

  it('names every status, and a type the catalogue no longer lists by its id', async () => {
    const line = { notes: null, provided_quantity: null, shortfall: null, outcome_note: null }
    server.use(
      http.get(LINES_PATH, () =>
        HttpResponse.json({
          event: { reference: MOCK_OPEN_EVENT_REFERENCE, name: 'Annual Partner Summit' },
          equipment_lines: [
            { ...line, id: 71, equipment_type_id: 77, quantity: 1, status: 'unavailable' },
            { ...line, id: 72, equipment_type_id: 1, quantity: 2, status: 'partially_fulfilled' },
            { ...line, id: 73, equipment_type_id: 2, quantity: 3, status: 'requested' },
            { ...line, id: 74, equipment_type_id: 3, quantity: 4, status: 'fulfilled' },
          ],
        }),
      ),
    )
    renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    await screen.findByRole('table', { name: 'Equipment lines' })
    expect(lineRows()).toEqual([
      ['Equipment type 77', '1', 'No notes', 'Unavailable'],
      ['Projector', '2', 'No notes', 'Partially fulfilled'],
      ['Microphone', '3', 'No notes', 'Awaiting Technical Support'],
      ['Lectern', '4', 'No notes', 'Fulfilled'],
    ])
  })

  it('says when nothing has been asked for yet', async () => {
    await openAsCoordinator(eventEquipmentPath(mockStatusEventReference('submitted')))

    expect(screen.getByText('No equipment has been asked for yet.')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Equipment lines' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add line' })).toBeInTheDocument()
  })

  it.each([
    ['the lines', LINES_PATH],
    ['the equipment types', '/api/equipment/types'],
  ])('shows the backend message when %s cannot be read', async (_what, path) => {
    server.use(
      http.get(path, () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'The equipment list is unavailable.' },
          { status: 500 },
        ),
      ),
    )
    renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })

    expect(await screen.findByRole('alert')).toHaveTextContent('The equipment list is unavailable.')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})

describe('SCRUM-37 equipment page: adding a line (AC1, AC3)', () => {
  it('offers the catalogue in the order the backend sent it', async () => {
    await openAsCoordinator()

    const options = within(screen.getByLabelText('Equipment type')).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual([
      'Choose equipment',
      'Lectern',
      'Microphone',
      'Projector',
    ])
  })

  it('sends the line, lists it, counts it in availability and clears the form', async () => {
    const requests = recordRequests()
    const { user } = await openAsCoordinator()

    await addLine(user, { type: 'Lectern', quantity: '2', notes: 'Stage left' })

    await waitFor(() => expect(lineRows()).toHaveLength(3))
    expect(await sentBody(requests, 'POST')).toEqual({
      equipment_type_id: 3,
      quantity: 2,
      notes: 'Stage left',
    })
    expect(lineRows()[2]).toEqual(['Lectern', '2', 'Stage left', 'Awaiting Technical Support'])
    await waitFor(() => expect(requestedInAvailability('Lectern')).toBe('2'))
    expect(screen.getByLabelText('Equipment type')).toHaveValue('')
    expect(screen.getByLabelText('Quantity')).toHaveValue(null)
    expect(screen.getByLabelText('Technical notes')).toHaveValue('')
  })

  it('leaves blank notes out', async () => {
    const requests = recordRequests()
    const { user } = await openAsCoordinator()

    await addLine(user, { type: 'Lectern', quantity: '1' })

    await waitFor(() => expect(lineRows()).toHaveLength(3))
    expect(await sentBody(requests, 'POST')).toEqual({ equipment_type_id: 3, quantity: 1 })
  })

  it("shows the backend's message under the quantity for zero, keeping what was typed (AC3)", async () => {
    const { user } = await openAsCoordinator()

    await addLine(user, { type: 'Lectern', quantity: '0' })

    expect(await screen.findByText('Quantity must be at least 1.')).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity')).toBeInvalid()
    expect(screen.getByLabelText('Quantity')).toHaveValue(0)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('sends nothing for blank fields and shows what the backend says is missing', async () => {
    const requests = recordRequests()
    const { user } = await openAsCoordinator()

    await addLine(user, {})

    await waitFor(() =>
      expect(screen.getAllByText('Missing data for required field.')).toHaveLength(2),
    )
    expect(await sentBody(requests, 'POST')).toEqual({})
    expect(screen.getByLabelText('Equipment type')).toBeInvalid()
    expect(screen.getByLabelText('Quantity')).toBeInvalid()
  })

  it('shows a refusal that is not about a field as an alert', async () => {
    const { user } = await openAsCoordinator()

    await addLine(user, { type: 'Projector', quantity: '1' })

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This event already has a line for that equipment type. Edit that line instead.',
    )
  })

  it('shows the refusal for an event whose equipment can no longer change', async () => {
    const { user } = await openAsCoordinator(
      eventEquipmentPath(mockStatusEventReference('confirmed')),
    )

    await addLine(user, { type: 'Lectern', quantity: '1' })

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Equipment can only be changed while the request is submitted, under review or approved.',
    )
  })
})

describe('SCRUM-37 equipment page: changing a line (AC2)', () => {
  async function startChanging(user: User, name: string) {
    await user.click(within(linesTable()).getByRole('button', { name: `Change ${name}` }))
    return screen.getByRole('form', { name: `Change ${name}` })
  }

  it('opens the line with its values in place of the add form', async () => {
    const { user } = await openAsCoordinator()

    const form = await startChanging(user, 'Projector')

    expect(within(form).getByLabelText('Equipment type')).toHaveValue('1')
    expect(within(form).getByLabelText('Quantity')).toHaveValue(8)
    expect(within(form).getByLabelText('Technical notes')).toHaveValue(PROJECTOR_NOTES)
    expect(screen.queryByRole('button', { name: 'Add line' })).not.toBeInTheDocument()
  })

  it('sends only what changed, shows the new quantity and closes', async () => {
    const requests = recordRequests()
    const { user } = await openAsCoordinator()
    const form = await startChanging(user, 'Projector')

    await user.clear(within(form).getByLabelText('Quantity'))
    await user.type(within(form).getByLabelText('Quantity'), '9')
    await user.click(within(form).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(lineRows()[0]?.[1]).toBe('9'))
    const patch = requests.find((request) => request.method === 'PATCH')
    expect(new URL(patch?.url ?? '').pathname).toBe(`${LINES_PATH}/41`)
    expect(await sentBody(requests, 'PATCH')).toEqual({ quantity: 9 })
    expect(screen.queryByRole('form', { name: 'Change Projector' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add line' })).toBeInTheDocument()
    await waitFor(() => expect(requestedInAvailability('Projector')).toBe('9'))
  })

  it('clears the notes and moves the line to another type', async () => {
    const requests = recordRequests()
    const { user } = await openAsCoordinator()
    const form = await startChanging(user, 'Projector')

    await user.clear(within(form).getByLabelText('Technical notes'))
    await user.selectOptions(within(form).getByLabelText('Equipment type'), 'Lectern')
    await user.click(within(form).getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(lineRows()[0]).toEqual(['Lectern', '8', 'No notes', 'Awaiting Technical Support']),
    )
    expect(await sentBody(requests, 'PATCH')).toEqual({ equipment_type_id: 3, notes: '' })
  })

  it('sends an empty change when nothing changed', async () => {
    const requests = recordRequests()
    const { user } = await openAsCoordinator()
    const form = await startChanging(user, 'Microphone')

    await user.click(within(form).getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(screen.queryByRole('form', { name: 'Change Microphone' })).not.toBeInTheDocument(),
    )
    expect(await sentBody(requests, 'PATCH')).toEqual({})
  })

  it("shows the backend's message for a quantity below what will be provided", async () => {
    const { user } = await openAsCoordinator()
    const form = await startChanging(user, 'Microphone')

    await user.clear(within(form).getByLabelText('Quantity'))
    await user.type(within(form).getByLabelText('Quantity'), '3')
    await user.click(within(form).getByRole('button', { name: 'Save changes' }))

    expect(
      await within(form).findByText(
        'Quantity cannot be below the 4 units Technical Support has said they will provide.',
      ),
    ).toBeInTheDocument()
    expect(within(form).getByLabelText('Quantity')).toBeInvalid()
  })

  it('shows a refusal that is not about a field as an alert, and stays open', async () => {
    refuseLineWith('patch', 'Equipment can only be changed while the request is submitted.')
    const { user } = await openAsCoordinator()
    const form = await startChanging(user, 'Projector')

    await user.click(within(form).getByRole('button', { name: 'Save changes' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent(
      'Equipment can only be changed while the request is submitted.',
    )
    expect(screen.getByRole('form', { name: 'Change Projector' })).toBeInTheDocument()
  })

  it('goes back to adding without sending anything on cancel', async () => {
    const requests = recordRequests()
    const { user } = await openAsCoordinator()
    const form = await startChanging(user, 'Projector')

    await user.click(within(form).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('form', { name: 'Change Projector' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add line' })).toBeInTheDocument()
    expect(requests.some((request) => request.method === 'PATCH')).toBe(false)
  })

  it('switches to another line with its own values', async () => {
    const { user } = await openAsCoordinator()
    await startChanging(user, 'Projector')

    const form = await startChanging(user, 'Microphone')

    expect(within(form).getByLabelText('Quantity')).toHaveValue(4)
    expect(within(form).getByLabelText('Technical notes')).toHaveValue('')
  })
})

describe('SCRUM-37 equipment page: removing a line (AC2)', () => {
  it('asks first, and keeps the line when told to', async () => {
    const requests = recordRequests()
    const { user } = await openAsCoordinator()

    await user.click(within(linesTable()).getByRole('button', { name: 'Remove Projector' }))
    expect(screen.getByText('Remove Projector from this event?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Keep it' }))

    expect(screen.queryByText('Remove Projector from this event?')).not.toBeInTheDocument()
    expect(lineRows()).toHaveLength(2)
    expect(requests.some((request) => request.method === 'DELETE')).toBe(false)
  })

  it('removes the line once confirmed, and availability no longer counts it', async () => {
    const requests = recordRequests()
    const { user } = await openAsCoordinator()

    // The second line, so removing the first by mistake would show.
    await user.click(within(linesTable()).getByRole('button', { name: 'Remove Microphone' }))
    await user.click(screen.getByRole('button', { name: 'Remove line' }))

    await waitFor(() => expect(lineRows().map((row) => row[0])).toEqual(['Projector']))
    const removal = requests.find((request) => request.method === 'DELETE')
    expect(new URL(removal?.url ?? '').pathname).toBe(`${LINES_PATH}/42`)
    expect(screen.queryByText('Remove Microphone from this event?')).not.toBeInTheDocument()
    await waitFor(() => expect(requestedInAvailability('Microphone')).toBe('0'))
  })

  it("shows the backend's refusal and keeps asking", async () => {
    refuseLineWith('delete', 'Equipment can only be changed while the request is approved.')
    const { user } = await openAsCoordinator()

    await user.click(within(linesTable()).getByRole('button', { name: 'Remove Microphone' }))
    await user.click(screen.getByRole('button', { name: 'Remove line' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Equipment can only be changed while the request is approved.',
    )
    expect(screen.getByText('Remove Microphone from this event?')).toBeInTheDocument()
    expect(lineRows()).toHaveLength(2)
  })
})

describe('SCRUM-48 equipment page: the outcome beside each line (AC1, AC2, AC5)', () => {
  it("shows the coordinator each line's outcome, and who reviewed it when", async () => {
    await openAsCoordinator()

    expect(within(linesTable()).getByRole('columnheader', { name: 'Outcome' })).toBeInTheDocument()
    expect(outcomeCell('Projector')).toHaveTextContent('Not reviewed yet')
    const microphone = within(outcomeCell('Microphone'))
    expect(microphone.getByText('4 of 4 provided')).toBeInTheDocument()
    expect(microphone.getByText('Reviewed by Tariq Hassan, 5 Oct, 10:00 am')).toBeInTheDocument()
  })

  it('shows the shortfall, the note and the reviewer for part or none of a request', async () => {
    const reviewed = {
      notes: null,
      reviewed_at: '2026-10-06T09:15:00+08:00',
    }
    server.use(
      http.get(LINES_PATH, () =>
        HttpResponse.json({
          event: { reference: MOCK_OPEN_EVENT_REFERENCE, name: 'Annual Partner Summit' },
          equipment_lines: [
            {
              ...reviewed,
              id: 81,
              equipment_type_id: 2,
              quantity: 10,
              status: 'partially_fulfilled',
              provided_quantity: 6,
              shortfall: 4,
              outcome_note: 'Four are out for repair; the venue has two more.',
              reviewed_by: 'Nadia Rahim',
            },
            {
              ...reviewed,
              id: 82,
              equipment_type_id: 3,
              quantity: 3,
              status: 'unavailable',
              provided_quantity: 0,
              shortfall: 3,
              outcome_note: 'Both lecterns are booked that evening.',
              // The reviewer's account is gone.
              reviewed_by: null,
            },
          ],
        }),
      ),
    )
    renderApp(OPEN_PAGE, { session: COORDINATOR })

    await screen.findByRole('table', { name: 'Equipment lines' })
    expect(statusOf('Microphone')).toBe('Partially fulfilled')
    const microphones = within(outcomeCell('Microphone'))
    expect(microphones.getByText('6 of 10 provided, short by 4')).toBeInTheDocument()
    expect(
      microphones.getByText('Four are out for repair; the venue has two more.'),
    ).toBeInTheDocument()
    expect(microphones.getByText('Reviewed by Nadia Rahim, 6 Oct, 9:15 am')).toBeInTheDocument()
    expect(statusOf('Lectern')).toBe('Unavailable')
    const lecterns = within(outcomeCell('Lectern'))
    expect(lecterns.getByText('0 of 3 provided, short by 3')).toBeInTheDocument()
    expect(lecterns.getByText('Both lecterns are booked that evening.')).toBeInTheDocument()
    expect(lecterns.getByText('Reviewed 6 Oct, 9:15 am')).toBeInTheDocument()
  })
})

describe('SCRUM-48 equipment page: recording an outcome (AC1, AC2, AC3, AC6)', () => {
  const OUTCOME_FORM = { name: 'Outcome for Projector' }

  async function openAsTechnicalSupport() {
    const rendered = renderApp(OPEN_PAGE, { session: TECHNICAL_SUPPORT })
    await screen.findByRole('table', { name: 'Equipment lines' })
    return rendered
  }

  /** Open the outcome form for `name`'s line with the button that says `action`. */
  async function openOutcome(user: User, action: 'Record' | 'Revise', name: string) {
    await user.click(
      within(linesTable()).getByRole('button', { name: `${action} outcome for ${name}` }),
    )
    return screen.getByRole('form', { name: `Outcome for ${name}` })
  }

  /** Fill in the Projector's outcome form and save it. A value left undefined is not typed. */
  async function recordProjector(user: User, values: { provided?: string; note?: string }) {
    const form = await openOutcome(user, 'Record', 'Projector')
    if (values.provided !== undefined) {
      await user.type(within(form).getByLabelText('Quantity provided'), values.provided)
    }
    if (values.note !== undefined) {
      await user.type(within(form).getByLabelText('Note for the coordinator'), values.note)
    }
    await user.click(within(form).getByRole('button', { name: 'Save outcome' }))
    return form
  }

  /** The one outcome sent: to the Projector line's own path, with its body. */
  async function sentOutcome(requests: Request[]) {
    const sent = requests.filter((request) => request.method === 'POST')
    expect(sent.map((request) => new URL(request.url).pathname)).toEqual([
      `${LINES_PATH}/41/outcome`,
    ])
    return sentBody(requests, 'POST')
  }

  it('offers Technical Support to record an outcome for a line without one, and revise one that has one', async () => {
    await openAsTechnicalSupport()

    const table = within(linesTable())
    expect(table.getByRole('button', { name: 'Record outcome for Projector' })).toHaveTextContent(
      'Record outcome',
    )
    expect(table.getByRole('button', { name: 'Revise outcome for Microphone' })).toHaveTextContent(
      'Revise outcome',
    )
  })

  it('gives the coordinator no outcome controls', async () => {
    await openAsCoordinator()

    expect(screen.queryByRole('button', { name: /outcome/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Review' })).not.toBeInTheDocument()
  })

  it('records part of a request with its note, and shows it beside the line (AC1)', async () => {
    const requests = recordRequests()
    const { user } = await openAsTechnicalSupport()

    const form = await recordProjector(user, { provided: '6', note: 'Two are being repaired.' })

    await waitFor(() => expect(form).not.toBeInTheDocument())
    expect(await sentOutcome(requests)).toEqual({
      provided_quantity: 6,
      note: 'Two are being repaired.',
    })
    expect(statusOf('Projector')).toBe('Partially fulfilled')
    const projector = within(outcomeCell('Projector'))
    expect(projector.getByText('6 of 8 provided, short by 2')).toBeInTheDocument()
    expect(projector.getByText('Two are being repaired.')).toBeInTheDocument()
    expect(projector.getByText('Reviewed by Tariq Hassan, 6 Oct, 9:15 am')).toBeInTheDocument()
  })

  it('says how many were asked for', async () => {
    const { user } = await openAsTechnicalSupport()

    const form = await openOutcome(user, 'Record', 'Projector')

    expect(within(form).getByText('8 asked for.')).toBeInTheDocument()
  })

  it("shows the backend's message under the note when part of it has none, and stays open (AC1)", async () => {
    const requests = recordRequests()
    const { user } = await openAsTechnicalSupport()

    const form = await recordProjector(user, { provided: '6' })

    expect(
      await within(form).findByText('A note is required unless the whole request can be provided.'),
    ).toBeInTheDocument()
    expect(await sentOutcome(requests)).toEqual({ provided_quantity: 6 })
    expect(within(form).getByLabelText('Note for the coordinator')).toBeInvalid()
    expect(within(form).queryByRole('alert')).not.toBeInTheDocument()
    expect(statusOf('Projector')).toBe('Awaiting Technical Support')
  })

  it('records the whole request with no note as fulfilled (AC2)', async () => {
    const { user } = await openAsTechnicalSupport()

    await recordProjector(user, { provided: '8' })

    await waitFor(() => expect(statusOf('Projector')).toBe('Fulfilled'))
    expect(within(outcomeCell('Projector')).getByText('8 of 8 provided')).toBeInTheDocument()
  })

  it('records none of it, with the reason, as unavailable (AC3)', async () => {
    const { user } = await openAsTechnicalSupport()

    await recordProjector(user, { provided: '0', note: 'All out on loan that week.' })

    await waitFor(() => expect(statusOf('Projector')).toBe('Unavailable'))
    const projector = within(outcomeCell('Projector'))
    expect(projector.getByText('0 of 8 provided, short by 8')).toBeInTheDocument()
    expect(projector.getByText('All out on loan that week.')).toBeInTheDocument()
  })

  it("shows the backend's message under the quantity for more than was asked for", async () => {
    const { user } = await openAsTechnicalSupport()

    const form = await recordProjector(user, { provided: '9' })

    expect(
      await within(form).findByText('Cannot provide more than was requested.'),
    ).toBeInTheDocument()
    expect(within(form).getByLabelText('Quantity provided')).toBeInvalid()
  })

  it('sends nothing for blank fields and shows what the backend says is missing', async () => {
    const requests = recordRequests()
    const { user } = await openAsTechnicalSupport()

    const form = await recordProjector(user, {})

    expect(await within(form).findByText('Missing data for required field.')).toBeInTheDocument()
    expect(await sentOutcome(requests)).toEqual({})
  })

  it('revises an outcome, opening with the one recorded (AC6)', async () => {
    const { user } = await openAsTechnicalSupport()
    await recordProjector(user, { provided: '6', note: 'Two are being repaired.' })
    await waitFor(() => expect(statusOf('Projector')).toBe('Partially fulfilled'))

    const form = await openOutcome(user, 'Revise', 'Projector')
    expect(within(form).getByLabelText('Quantity provided')).toHaveValue(6)
    expect(within(form).getByLabelText('Note for the coordinator')).toHaveValue(
      'Two are being repaired.',
    )
    await user.clear(within(form).getByLabelText('Quantity provided'))
    await user.type(within(form).getByLabelText('Quantity provided'), '8')
    await user.clear(within(form).getByLabelText('Note for the coordinator'))
    await user.click(within(form).getByRole('button', { name: 'Save outcome' }))

    await waitFor(() => expect(statusOf('Projector')).toBe('Fulfilled'))
    expect(within(outcomeCell('Projector')).getByText('8 of 8 provided')).toBeInTheDocument()
  })

  it('opens a line met in full with its quantity and an empty note', async () => {
    const { user } = await openAsTechnicalSupport()

    const form = await openOutcome(user, 'Revise', 'Microphone')

    expect(within(form).getByLabelText('Quantity provided')).toHaveValue(4)
    expect(within(form).getByLabelText('Note for the coordinator')).toHaveValue('')
  })

  it('switches to another line with its own outcome', async () => {
    const { user } = await openAsTechnicalSupport()
    await openOutcome(user, 'Record', 'Projector')

    const form = await openOutcome(user, 'Revise', 'Microphone')

    expect(within(form).getByLabelText('Quantity provided')).toHaveValue(4)
    expect(screen.queryByRole('form', OUTCOME_FORM)).not.toBeInTheDocument()
  })

  it('shows a refusal that is not about a field as an alert, and stays open (AC8)', async () => {
    server.use(
      http.post(`${LINES_PATH}/:lineId/outcome`, () =>
        HttpResponse.json(
          {
            error: 'equipment_outcome_not_allowed',
            message: 'An outcome cannot be recorded on a cancelled event.',
          },
          { status: 409 },
        ),
      ),
    )
    const { user } = await openAsTechnicalSupport()

    const form = await recordProjector(user, { provided: '8' })

    expect(await within(form).findByRole('alert')).toHaveTextContent(
      'An outcome cannot be recorded on a cancelled event.',
    )
    expect(screen.getByRole('form', OUTCOME_FORM)).toBeInTheDocument()
  })

  it('closes without sending anything on cancel', async () => {
    const requests = recordRequests()
    const { user } = await openAsTechnicalSupport()
    const form = await openOutcome(user, 'Record', 'Projector')

    await user.click(within(form).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('form', OUTCOME_FORM)).not.toBeInTheDocument()
    expect(requests.some((request) => request.method === 'POST')).toBe(false)
  })
})
