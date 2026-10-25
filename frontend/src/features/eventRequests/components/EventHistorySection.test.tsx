import { screen, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import { coordinatorEventPath, organiserRequestPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'

import { findRegion } from '../test/recordPage'

/**
 * SCRUM-33 AC4, AC5: an event's history on its record, to its coordinator and to an organiser
 * of its organisation, each entry saying what changed, who did it and when, as the backend sends
 * it (ADR-0025, ADR-0076). The mock (src/mocks/handlers/eventRecordSections.ts) holds four
 * entries for Chloe's EVR-7K2M9QXA, one an internal planning note the organiser isn't shown,
 * and six for Marcus's EVR-W9CR5E7M, assigned by the system before the Lead existed.
 */

const ORGANISER = mockSessionFor(MOCK_ACCOUNTS.organiser)
const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
const HISTORY_PATH = `/api/events/requests/${PARTNER_SUMMIT}/history`

/** The history's entries, once they have loaded. */
async function historyEntries(): Promise<HTMLElement[]> {
  const history = await findRegion('History')
  const list = await within(history).findByRole('list')
  return within(list).getAllByRole('listitem')
}

function serveHistory(entries: unknown[]) {
  server.use(http.get(HISTORY_PATH, () => HttpResponse.json({ history: entries })))
}

describe('SCRUM-33 AC5 the history on an event record', () => {
  it('shows the coordinator every entry, oldest first, each with who and when', async () => {
    renderApp(coordinatorEventPath(PARTNER_SUMMIT), { session: COORDINATOR })

    const entries = await historyEntries()

    expect(entries.map((entry) => within(entry).getByRole('heading').textContent)).toEqual([
      'Coordinator assigned',
      'Review started',
      'Planning notes changed',
      'Expected attendance changed',
    ])
    const [assigned] = entries as [HTMLElement]
    expect(assigned).toHaveTextContent('CoordinatorChloe Lim')
    expect(assigned).toHaveTextContent('6 Oct, 2:00 pm · Leon Goh')
  })

  it('gives a change its field, the value before and after, and marks it significant (AC2, AC4)', async () => {
    renderApp(coordinatorEventPath(PARTNER_SUMMIT), { session: COORDINATOR })

    const change = (await historyEntries())[3] as HTMLElement

    expect(within(change).getByText('Before').nextElementSibling).toHaveTextContent('200')
    expect(within(change).getByText('After').nextElementSibling).toHaveTextContent('250')
    expect(within(change).getByText('Significant change')).toBeInTheDocument()
    expect(change).toHaveTextContent('8 Oct, 10:15 am · Chloe Lim')
  })

  it('does not mark a change the backend did not call significant', async () => {
    renderApp(coordinatorEventPath(PARTNER_SUMMIT), { session: COORDINATOR })

    const note = (await historyEntries())[2] as HTMLElement

    expect(within(note).queryByText('Significant change')).not.toBeInTheDocument()
  })

  it('shows an organiser every entry the backend sends them (SCRUM-24 AC10)', async () => {
    renderApp(organiserRequestPath(PARTNER_SUMMIT), { session: ORGANISER })

    const entries = await historyEntries()

    expect(entries).toHaveLength(4)
    const history = await findRegion('History')
    expect(within(history).getByText('Planning notes changed')).toBeInTheDocument()
  })

  it('says only when for an entry made by the system', async () => {
    renderApp(organiserRequestPath('EVR-W9CR5E7M'), { session: ORGANISER })

    const [assigned] = (await historyEntries()) as [HTMLElement]

    expect(within(assigned).getByText('28 Sept, 3:00 pm')).toBeInTheDocument()
    expect(assigned).not.toHaveTextContent('·')
  })

  it('says so when nothing has been recorded yet', async () => {
    renderApp(organiserRequestPath('EVR-Q4ZT6N1B'), { session: ORGANISER })

    const history = await findRegion('History')

    expect(
      await within(history).findByText('Nothing has been recorded for this event yet.'),
    ).toBeInTheDocument()
  })

  it('shows a kind of entry it does not know yet as a plain line, and the rest as usual', async () => {
    serveHistory([
      {
        kind: 'venue_hold_expired',
        occurred_at: '2026-10-09T09:00:00+08:00',
        actor_name: 'Vera Goh',
        details: { venue_id: 12 },
      },
      {
        kind: 'review_started',
        occurred_at: '2026-10-10T09:00:00+08:00',
        actor_name: 'Chloe Lim',
        details: {},
      },
    ])
    renderApp(coordinatorEventPath(PARTNER_SUMMIT), { session: COORDINATOR })

    const [unknown, known] = (await historyEntries()) as [HTMLElement, HTMLElement]

    expect(within(unknown).getByRole('heading')).toHaveTextContent('Venue hold expired')
    expect(unknown).toHaveTextContent('9 Oct, 9:00 am · Vera Goh')
    expect(within(known).getByRole('heading')).toHaveTextContent('Review started')
  })

  it("shows the backend's message when the history can't be read, and the record still", async () => {
    server.use(
      http.get(HISTORY_PATH, () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'The history is unavailable right now.' },
          { status: 500 },
        ),
      ),
    )
    renderApp(coordinatorEventPath(PARTNER_SUMMIT), { session: COORDINATOR })

    const history = await findRegion('History')

    expect(await within(history).findByRole('alert')).toHaveTextContent(
      'The history is unavailable right now.',
    )
    expect(screen.getByRole('region', { name: 'About the event' })).toBeInTheDocument()
  })

  it('says it is loading while the history is on its way', async () => {
    server.use(
      http.get(HISTORY_PATH, async () => {
        await delay('infinite')
      }),
    )
    renderApp(coordinatorEventPath(PARTNER_SUMMIT), { session: COORDINATOR })

    const history = await findRegion('History')

    expect(within(history).getByRole('status')).toHaveTextContent('Loading the history')
  })
})
