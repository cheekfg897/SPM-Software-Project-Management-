import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { coordinatorEventPath, organiserRequestPath, staffEventPath } from '@/config/routes'
import {
  decideChangeRequest,
  decideEventRequest,
  editEventRequest,
  fetchEventRequest,
  raiseChangeRequest,
} from '@/features/eventRequests/api'
import type { RecordVenueArrangement } from '@/features/eventRequests/api'
import type { EquipmentReservation } from '@/features/equipment/api'
import { MOCK_ACCOUNTS, mockSessionFor, mockTokenFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { everyArrangementForRecord } from '@/mocks/handlers/booking'
import { errorResponse } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { findRegion } from '../test/recordPage'

/**
 * SCRUM-57: the event's coordinator reviews the organiser's Pending change request on the event
 * page, beside what the event holds now, its venue arrangements and its reserved equipment
 * (AC1), and approves or rejects it with a reason (AC2, AC3). The decision shows on every record
 * (AC6). Every refusal is the backend's, shown as it comes: a request a later edit overtook
 * (AC8), and the event's own decision while a request is Pending (AC9). The mock in
 * src/mocks/handlers/changeRequests.ts keeps the requests. Omar wrote EVR-7K2M9QXA "Partner
 * Summit" (under review, coordinated by Chloe: 12 Nov, 9:00 am to 5:00 pm, 250 expected). The
 * mock's "now" is 5 Oct, 12:00 pm.
 */

const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
/** The Harbour Gala: its mock arrangements are a dinner, a reception and a withdrawn overflow. */
const HARBOUR_GALA = 'EVR-BOOK0112'
const CHLOE = MOCK_ACCOUNTS.coordinator
const REASON = 'The keynote speaker lands later.'
const DECIDE = 'Decide the change request'
const NOT_FOUND = 'Event request not found.'
const STALE_MESSAGE =
  "This change request can't be approved because the event has changed since it was raised. " +
  'Expected attendance: 250 when the change was requested, 200 now. Reject it, and the ' +
  'organiser can raise a new one.'
const PROJECTORS: EquipmentReservation = {
  id: 7,
  equipment_type_id: 1,
  equipment_type_name: 'Projector',
  quantity: 2,
  starts_at: '2026-11-12T09:00:00+08:00',
  ends_at: '2026-11-12T17:00:00+08:00',
  reserved_by: 'Tess Tech',
  created_at: '2026-10-02T10:00:00+08:00',
  needs_attention: false,
  preparation_status: 'not_started',
  preparation_notes: null,
}

/** As Omar, ask for the Summit to start at 10:00 for 300 people; answers the request's id. */
async function omarAsksForALaterStart() {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.organiser))
  const raised = await raiseChangeRequest(PARTNER_SUMMIT, {
    start_time: '10:00',
    expected_attendance: 300,
    reason: REASON,
  })
  return raised.id
}

function openAs(account: MockAccount, path: string) {
  return renderApp(path, { session: mockSessionFor(account) })
}

/** Chloe's Summit page: answers the decision panel of the change Omar has asked for. */
async function openDecisionPanel() {
  const { user } = openAs(CHLOE, coordinatorEventPath(PARTNER_SUMMIT))
  const panel = within(await findRegion(DECIDE))
  return { user, panel }
}

/** Chloe's Summit page, once Omar has asked for his change: answers the decision panel. */
async function openForDecision() {
  await omarAsksForALaterStart()
  return openDecisionPanel()
}

/** As `openForDecision`, with the record sending these arrangements instead of its own. */
async function openWithArrangements(arrangements: RecordVenueArrangement[] | undefined) {
  await omarAsksForALaterStart()
  sendRequestsAs(mockTokenFor(CHLOE))
  const record = await fetchEventRequest(PARTNER_SUMMIT)
  server.use(
    http.get(`/api/events/requests/${PARTNER_SUMMIT}`, () =>
      HttpResponse.json({ ...record, venue_arrangements: arrangements }),
    ),
  )
  return openDecisionPanel()
}

describe('SCRUM-57 AC1 reviewing a change request', () => {
  it('shows each change beside what the event holds now', async () => {
    const { panel } = await openForDecision()

    expect(panel.getByText('Start time')).toBeInTheDocument()
    expect(panel.getByText('9:00 am now → 10:00 am')).toBeInTheDocument()
    expect(panel.getByText('250 now → 300')).toBeInTheDocument()
  })

  it('lists every venue booking of the event, in the panel and read-only', async () => {
    const { panel } = await openWithArrangements(everyArrangementForRecord(HARBOUR_GALA))

    expect(panel.getByText(/Gala dinner/)).toBeInTheDocument()
    expect(panel.getByText(/Drinks reception/)).toBeInTheDocument()
    expect(panel.getByText(/Overflow room/)).toBeInTheDocument()
    const buttons = panel.getAllByRole('button').map((button) => button.textContent)
    expect(buttons).toEqual(['Approve', 'Reject'])
  })

  it.each([
    { sent: 'an empty list', arrangements: [] },
    { sent: 'no list', arrangements: undefined },
  ])('says no venue is arranged when the record sends $sent', async ({ arrangements }) => {
    const { panel } = await openWithArrangements(arrangements)

    expect(panel.getByText('No venue is arranged for this event yet.')).toBeInTheDocument()
  })

  it('lists the equipment reserved for the event', async () => {
    server.use(
      http.get(`/api/equipment/events/${PARTNER_SUMMIT}/reservations`, () =>
        HttpResponse.json([PROJECTORS]),
      ),
    )

    const { panel } = await openForDecision()

    expect(await panel.findByText('2 × Projector')).toBeInTheDocument()
  })

  it('says when no equipment is reserved', async () => {
    const { panel } = await openForDecision()

    expect(await panel.findByText('No equipment is reserved for this event.')).toBeInTheDocument()
  })

  it("shows the backend's refusal when the reserved equipment can't be read", async () => {
    server.use(
      http.get(`/api/equipment/events/${PARTNER_SUMMIT}/reservations`, () =>
        errorResponse(404, 'not_found', NOT_FOUND),
      ),
    )

    const { panel } = await openForDecision()

    expect(await panel.findByRole('alert')).toHaveTextContent(NOT_FOUND)
  })

  it('offers no decision to the organiser', async () => {
    await omarAsksForALaterStart()
    openAs(MOCK_ACCOUNTS.organiser, organiserRequestPath(PARTNER_SUMMIT))

    await findRegion('Change requests')
    expect(screen.queryByRole('region', { name: DECIDE })).not.toBeInTheDocument()
  })

  it('offers no decision to a coordinator the event is not assigned to', async () => {
    await omarAsksForALaterStart()
    openAs(MOCK_ACCOUNTS.freshCoordinator, coordinatorEventPath(PARTNER_SUMMIT))

    expect(await screen.findByRole('alert')).toHaveTextContent(NOT_FOUND)
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
  })
})

describe('SCRUM-57 AC2, AC3, AC6 deciding a change request', () => {
  it('approves it: the event takes the new values and the request shows who approved it', async () => {
    const { user, panel } = await openForDecision()
    const requests = recordRequests()

    await user.type(panel.getByLabelText('Reason'), 'The hall holds 300.')
    await user.click(panel.getByRole('button', { name: 'Approve' }))

    const listed = await findRegion('Change requests')
    expect(await within(listed).findByText('Approved')).toBeInTheDocument()
    expect(listed).toHaveTextContent('Approved by Chloe Lim, 5 Oct, 12:00 pm')
    expect(listed).toHaveTextContent('The hall holds 300.')
    expect(await findRegion('About the event')).toHaveTextContent('Expected attendance300')
    expect(screen.queryByRole('region', { name: DECIDE })).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(
      new RegExp(`/api/events/requests/${PARTNER_SUMMIT}/change-requests/\\d+/decide$`),
    )
    await expect(sent?.json()).resolves.toEqual({
      outcome: 'approved',
      reason: 'The hall holds 300.',
    })
  })

  it("shows the backend's message under the box when a rejection has no reason", async () => {
    const { user, panel } = await openForDecision()

    await user.click(panel.getByRole('button', { name: 'Reject' }))

    expect(await panel.findByText('Say why the change request is rejected.')).toBeInTheDocument()
  })

  it('rejects it with a reason, leaving the event as it was', async () => {
    const { user, panel } = await openForDecision()

    await user.type(panel.getByLabelText('Reason'), 'The hall holds 250.')
    await user.click(panel.getByRole('button', { name: 'Reject' }))

    const listed = await findRegion('Change requests')
    expect(await within(listed).findByText('Rejected')).toBeInTheDocument()
    expect(listed).toHaveTextContent('Rejected by Chloe Lim, 5 Oct, 12:00 pm')
    expect(listed).toHaveTextContent('The hall holds 250.')
    expect(await findRegion('About the event')).toHaveTextContent('Expected attendance250')
  })

  it('shows the organiser the decision and its reason (AC6)', async () => {
    const id = await omarAsksForALaterStart()
    sendRequestsAs(mockTokenFor(CHLOE))
    await decideChangeRequest(PARTNER_SUMMIT, id, {
      outcome: 'rejected',
      reason: 'The hall holds 250.',
    })

    openAs(MOCK_ACCOUNTS.organiser, organiserRequestPath(PARTNER_SUMMIT))

    const listed = await findRegion('Change requests')
    expect(listed).toHaveTextContent('Rejected by Chloe Lim, 5 Oct, 12:00 pm')
    expect(listed).toHaveTextContent('The hall holds 250.')
  })

  it('shows staff the requests on the read-only record', async () => {
    await omarAsksForALaterStart()

    openAs(MOCK_ACCOUNTS.lead, staffEventPath(PARTNER_SUMMIT))

    const listed = await findRegion('Change requests')
    expect(within(listed).getByText('Pending')).toBeInTheDocument()
    expect(within(listed).queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('SCRUM-57 AC8, AC9 the refusals, as the backend words them', () => {
  it('says which field moved when a later edit overtook the request, and keeps it Pending', async () => {
    // Approved first: before that, the coordinator can't edit it directly (SCRUM-110).
    sendRequestsAs(mockTokenFor(CHLOE))
    await decideEventRequest(PARTNER_SUMMIT, { outcome: 'approved' })
    await omarAsksForALaterStart()
    sendRequestsAs(mockTokenFor(CHLOE))
    await editEventRequest(PARTNER_SUMMIT, { expected_attendance: 200 })
    const { user } = openAs(CHLOE, coordinatorEventPath(PARTNER_SUMMIT))
    const panel = within(await findRegion(DECIDE))

    await user.click(panel.getByRole('button', { name: 'Approve' }))

    expect(await panel.findByRole('alert')).toHaveTextContent(STALE_MESSAGE)
    expect(within(await findRegion('Change requests')).getByText('Pending')).toBeInTheDocument()
  })

  it("refuses the event's own decision while the request is Pending", async () => {
    await omarAsksForALaterStart()
    const { user } = openAs(CHLOE, coordinatorEventPath(PARTNER_SUMMIT))
    const decide = within(await findRegion('Decide'))

    await user.click(decide.getByRole('button', { name: 'Approve' }))

    expect(await decide.findByRole('alert')).toHaveTextContent(
      'The organiser has a change request waiting for your decision. Decide the change request first.',
    )
  })
})
