import { screen, waitFor, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { OTHER_STAFF } from '../test/otherStaff'
import { bodyOf } from '../test/venueFormSteps'

const VENUE_STAFF = mockSessionFor(MOCK_ACCOUNTS.venueStaff)
/** Marina Hall's page on 10 to 12 Nov, written out so a wrong path builder can't agree. */
const MARINA_PAGE = '/venues/1?from=2026-11-10&to=2026-11-12'
const BOARDROOM_PAGE = '/venues/2?from=2026-11-10&to=2026-11-10'
const CONFLICT_HEADING = 'Blocked. It cuts into these confirmed bookings, which are still booked:'

type User = ReturnType<typeof renderApp>['user']

async function blocksSection() {
  return within(await screen.findByRole('region', { name: 'Blocks' }))
}

async function blockVenue(user: User, start: string, end: string, reason: string) {
  const section = await blocksSection()
  await user.type(section.getByLabelText('Starts'), start)
  await user.type(section.getByLabelText('Ends'), end)
  await user.type(section.getByLabelText('Reason'), reason)
  await user.click(section.getByRole('button', { name: 'Block venue' }))
}

/** The text of each period the calendar lists on one day. */
async function periodsOn(dayName: string) {
  const day = await screen.findByRole('region', { name: dayName })
  return within(day)
    .queryAllByRole('listitem')
    .map((period) => period.textContent)
}

describe('SCRUM-34 blocking a venue (AC1)', () => {
  it('lists the venue’s blocks with their reasons and times', async () => {
    renderApp(MARINA_PAGE, { session: VENUE_STAFF })

    const list = within(await screen.findByRole('list', { name: 'Blocks' }))

    const blocks = list.getAllByRole('listitem')
    expect(blocks).toHaveLength(1)
    expect(blocks[0]).toHaveTextContent('Stage lighting repair')
    expect(blocks[0]).toHaveTextContent('10 Nov, 5:30 pm – 10 Nov, 8:00 pm')
  })

  it('sends the times as typed, in business time, and the block then shows in the list and the calendar', async () => {
    const requests = recordRequests()
    const { user } = renderApp(MARINA_PAGE, { session: VENUE_STAFF })

    await blockVenue(user, '2026-11-12T10:00', '2026-11-12T11:30', 'Fire alarm test')

    expect(await bodyOf(requests, 'POST')).toEqual({
      start_time: '2026-11-12T10:00',
      end_time: '2026-11-12T11:30',
      reason: 'Fire alarm test',
    })
    await waitFor(async () =>
      expect(await periodsOn('Thursday 12 Nov')).toEqual([
        'Blocked 10:00 am – 11:30 am Fire alarm test',
      ]),
    )
    const list = within(screen.getByRole('list', { name: 'Blocks' }))
    expect(list.getByText('Fire alarm test')).toBeInTheDocument()
    expect((await blocksSection()).getByLabelText('Reason')).toHaveValue('')
    expect(screen.queryByText(CONFLICT_HEADING)).not.toBeInTheDocument()
  })

  it('shows the backend messages under the fields it refused', async () => {
    const { user } = renderApp(MARINA_PAGE, { session: VENUE_STAFF })
    const section = await blocksSection()

    await user.click(section.getByRole('button', { name: 'Block venue' }))

    expect(await section.findByText('Must not be blank.')).toBeInTheDocument()
    expect(section.getByLabelText('Starts')).toHaveAccessibleDescription('Not a valid datetime.')
    expect(section.getByLabelText('Ends')).toHaveAccessibleDescription('Not a valid datetime.')
  })

  it('shows the backend message when the end is before the start', async () => {
    const { user } = renderApp(MARINA_PAGE, { session: VENUE_STAFF })

    await blockVenue(user, '2026-11-12T10:00', '2026-11-12T09:00', 'Typo')

    const section = await blocksSection()
    expect(await section.findByText('end_time must be after start_time.')).toBeInTheDocument()
    expect(section.getByLabelText('Ends')).toBeInvalid()
  })
})

describe('SCRUM-34 blocking over confirmed bookings (AC2, ADR-0016)', () => {
  it('saves the block and names each booking it cuts into, with the period it holds the venue', async () => {
    const { user } = renderApp(MARINA_PAGE, { session: VENUE_STAFF })

    await blockVenue(user, '2026-11-10T11:00', '2026-11-10T14:00', 'Fire alarm test')

    const report = await screen.findByRole('region', { name: CONFLICT_HEADING })
    expect(
      within(report)
        .getAllByRole('listitem')
        .map((line) => line.textContent),
    ).toEqual([
      'Booking 512 for event 101, 10 Nov, 8:30 am – 12:30 pm',
      'Booking 511 for event 105, 10 Nov, 12:30 pm – 5:30 pm',
    ])
  })

  it('says when a booking it cuts into has no event', async () => {
    const { user } = renderApp(BOARDROOM_PAGE, { session: VENUE_STAFF })

    await blockVenue(user, '2026-11-10T08:00', '2026-11-10T09:00', 'Projector swap')

    expect(
      await screen.findByText('Booking 505, with no linked event, 10 Nov, 8:50 am – 12:10 pm'),
    ).toBeInTheDocument()
  })
})

describe('SCRUM-34 removing a block (AC4)', () => {
  it('removes the block, which leaves the list and frees the period in the calendar', async () => {
    const { user } = renderApp(MARINA_PAGE, { session: VENUE_STAFF })

    await user.click(
      await screen.findByRole('button', { name: 'Remove the block for Stage lighting repair' }),
    )

    expect(await screen.findByText('The venue has no blocks.')).toBeInTheDocument()
    await waitFor(async () =>
      expect(
        (await periodsOn('Tuesday 10 Nov')).some((period) => period?.startsWith('Blocked')),
      ).toBe(false),
    )
  })

  it('removes the block asked for, not the one listed above it', async () => {
    const requests = recordRequests()
    const { user } = renderApp(MARINA_PAGE, { session: VENUE_STAFF })
    await blockVenue(user, '2026-11-12T10:00', '2026-11-12T11:30', 'Fire alarm test')

    await user.click(
      await screen.findByRole('button', { name: 'Remove the block for Fire alarm test' }),
    )

    await waitFor(() =>
      expect(screen.getByRole('list', { name: 'Blocks' })).not.toHaveTextContent('Fire alarm test'),
    )
    expect(screen.getByRole('list', { name: 'Blocks' })).toHaveTextContent('Stage lighting repair')
    const removal = requests.find((request) => request.method === 'DELETE')
    expect(new URL(removal?.url ?? 'http://none').pathname).toBe('/api/venues/1/blocks/800')
  })

  it('marks only the block being removed as busy while the backend answers', async () => {
    server.use(http.delete('/api/venues/1/blocks/:blockId', () => delay('infinite')))
    const { user } = renderApp(MARINA_PAGE, { session: VENUE_STAFF })
    await blockVenue(user, '2026-11-12T10:00', '2026-11-12T11:30', 'Fire alarm test')
    const removeNew = await screen.findByRole('button', {
      name: 'Remove the block for Fire alarm test',
    })

    await user.click(removeNew)

    await waitFor(() => expect(removeNew).toHaveAttribute('aria-busy', 'true'))
    expect(
      screen.getByRole('button', { name: 'Remove the block for Stage lighting repair' }),
    ).toHaveAttribute('aria-busy', 'false')
  })

  it('shows the backend message when a removal is refused, and keeps the block', async () => {
    server.use(
      http.delete('/api/venues/1/blocks/71', () =>
        HttpResponse.json({ error: 'not_found', message: 'Block not found.' }, { status: 404 }),
      ),
    )
    const { user } = renderApp(MARINA_PAGE, { session: VENUE_STAFF })

    await user.click(
      await screen.findByRole('button', { name: 'Remove the block for Stage lighting repair' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('Block not found.')
    expect(screen.getByRole('list', { name: 'Blocks' })).toHaveTextContent('Stage lighting repair')
  })
})

describe('SCRUM-34 only Venue Staff see and change blocks', () => {
  it.each(OTHER_STAFF)('shows $full_name the calendar but no blocks section', async (account) => {
    renderApp(MARINA_PAGE, { session: mockSessionFor(account) })

    await screen.findByRole('region', { name: 'Tuesday 10 Nov' })

    expect(screen.queryByRole('region', { name: 'Blocks' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Block venue' })).not.toBeInTheDocument()
  })

  it('says it is loading the blocks, then shows the backend message when they cannot be read', async () => {
    server.use(
      http.get('/api/venues/1/blocks', () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'Blocks are unavailable.' },
          { status: 500 },
        ),
      ),
    )
    renderApp(MARINA_PAGE, { session: VENUE_STAFF })

    expect(await screen.findByText('Loading blocks…')).toBeInTheDocument()
    expect(await screen.findByText('Blocks are unavailable.')).toBeInTheDocument()
  })
})
