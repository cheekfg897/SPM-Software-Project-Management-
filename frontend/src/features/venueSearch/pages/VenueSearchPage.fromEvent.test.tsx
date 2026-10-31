import { screen } from '@testing-library/react'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { venueSearchForEventPath } from '../searchParams'
import { search, searchesSent, typeInto } from '../test/searchForm'

/**
 * SCRUM-90: a coordinator opens venue search from one of their events, with the filters its
 * recorded details can fill already filled in (ADR-0124). The events come from the mock in
 * src/mocks/handlers/eventRequests.ts: Chloe coordinates EVR-7K2M9QXA "Partner Summit" (12 Nov,
 * 9:00 to 17:00, for 250, venue requirements only) and EVR-BOOK0101 (accessibility needs only);
 * Marcus coordinates EVR-W9CR5E7M, which she may not open.
 */

const COORDINATOR = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }
const PARTNER_SUMMIT = venueSearchForEventPath('EVR-7K2M9QXA')

type View = ReturnType<typeof renderApp>

/** The note beside the filters the event could not fill, once the event has arrived. */
function eventNote(name: string): Promise<HTMLElement> {
  return screen.findByRole('region', { name: `What ${name} asked for` })
}

/** Open the search from Partner Summit and wait until its details fill the form. */
async function openFromPartnerSummit(): Promise<View> {
  const view = renderApp(PARTNER_SUMMIT, COORDINATOR)
  await eventNote('Partner Summit')
  return view
}

describe('SCRUM-90 venue search opened from an event', () => {
  it('says it is loading the event before its details arrive', async () => {
    renderApp(PARTNER_SUMMIT, COORDINATOR)

    expect(await screen.findByRole('status')).toHaveTextContent('Loading the event')
  })

  it("fills in the period and minimum capacity from the event's details (AC1, AC2)", async () => {
    await openFromPartnerSummit()

    expect(screen.getByLabelText('Date')).toHaveValue('2026-11-12')
    expect(screen.getByLabelText('Start time')).toHaveValue('09:00')
    expect(screen.getByLabelText('End time')).toHaveValue('17:00')
    expect(screen.getByLabelText('End date')).toHaveValue('')
    expect(screen.getByLabelText('Minimum capacity')).toHaveValue(250)
  })

  it('searches nothing until the coordinator asks, so they can check the filters first (AC4)', async () => {
    const requests = recordRequests()

    await openFromPartnerSummit()

    expect(searchesSent(requests)).toHaveLength(0)
    expect(screen.queryByRole('heading', { name: 'Venues that match' })).not.toBeInTheDocument()
  })

  it("leaves layout, facilities and accessibility empty, with the event's own words beside them (AC3)", async () => {
    await openFromPartnerSummit()

    expect(screen.getByLabelText('Room layout')).toHaveValue('')
    expect(screen.getByLabelText('Facilities')).toHaveValue('')
    expect(screen.getByLabelText('Accessibility requirements')).toHaveValue('')
    const note = await eventNote('Partner Summit')
    expect(note).toHaveTextContent(
      'Room layout, facilities and accessibility are not filled in from the event',
    )
    expect(note).toHaveTextContent('Venue requirementsA main hall for 250 and four breakout rooms.')
    expect(note).toHaveTextContent('Accessibility needsNone recorded')
  })

  it("shows the event's accessibility needs as it wrote them (AC3)", async () => {
    renderApp(venueSearchForEventPath('EVR-BOOK0101'), COORDINATOR)

    const note = await eventNote('Harbourfront Careers Fair')
    expect(note).toHaveTextContent('Accessibility needsStep-free access')
    expect(note).toHaveTextContent('Venue requirementsNone recorded')
  })

  it('leads back to the event', async () => {
    await openFromPartnerSummit()

    expect(screen.getByRole('link', { name: 'Back to the event' })).toHaveAttribute(
      'href',
      '/events/EVR-7K2M9QXA',
    )
  })

  it('searches with whatever the coordinator changed and set, keeping the event in the URL (AC4)', async () => {
    const requests = recordRequests()
    const view = await openFromPartnerSummit()

    await typeInto(view, 'Minimum capacity', '300')
    await view.user.selectOptions(screen.getByLabelText('Room layout'), 'Theatre')
    await view.user.type(screen.getByLabelText('Accessibility requirements'), 'step-free access')
    await view.user.click(screen.getByRole('button', { name: 'Search venues' }))

    await screen.findByRole('heading', { name: 'Venues that match' })
    const sent = searchesSent(requests)
    expect(sent).toHaveLength(1)
    expect(await sent[0]?.json()).toEqual({
      start_time: '2026-11-12T09:00:00+08:00',
      end_time: '2026-11-12T17:00:00+08:00',
      min_capacity: 300,
      location: null,
      required_layout: 'theatre',
      required_facilities: [],
      required_accessibility: ['step-free access'],
    })
    const params = view.router.state.location.search
    expect(params).toContain('for_event=EVR-7K2M9QXA')
    expect(params).toContain('min_capacity=300')
    expect(await eventNote('Partner Summit')).toBeInTheDocument()
  })

  it("shows the filters in the URL rather than the event's once the coordinator has searched", async () => {
    const requests = recordRequests()

    renderApp(
      `${PARTNER_SUMMIT}&date=2026-11-20&start=10:00&end=12:00&min_capacity=40`,
      COORDINATOR,
    )

    await eventNote('Partner Summit')
    expect(screen.getByLabelText('Date')).toHaveValue('2026-11-20')
    expect(screen.getByLabelText('Minimum capacity')).toHaveValue(40)
    await screen.findByRole('heading', { name: 'Venues that match' })
    const sent = (await searchesSent(requests).at(-1)?.json()) as Record<string, unknown>
    expect(sent.start_time).toBe('2026-11-20T10:00:00+08:00')
    expect(sent.min_capacity).toBe(40)
  })

  it("shows the backend's message for an event the coordinator may not open, and still searches", async () => {
    const view = renderApp(venueSearchForEventPath('EVR-W9CR5E7M'), COORDINATOR)

    expect(await screen.findByRole('alert')).toHaveTextContent('Event request not found.')
    expect(screen.getByLabelText('Date')).toHaveValue('')
    expect(screen.queryByRole('region', { name: /asked for/ })).not.toBeInTheDocument()
    await search(view)
    expect(await screen.findByRole('heading', { name: 'Venues that match' })).toBeInTheDocument()
  })
})
