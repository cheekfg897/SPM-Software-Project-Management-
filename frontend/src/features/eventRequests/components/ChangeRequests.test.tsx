import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { coordinatorEventPath, organiserRequestPath } from '@/config/routes'
import type { ChangeRequest } from '@/features/eventRequests/api'
import { fetchEventRequest } from '@/features/eventRequests/api'
import { MOCK_ACCOUNTS, mockSessionFor, mockTokenFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { errorResponse } from '@/mocks/responses'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { findRegion, serveRecordInStatus, statusShownFor } from '../test/recordPage'

/**
 * SCRUM-56: the organiser who submitted an event asks for a change to it from its page, saying
 * what should change and why, and sees each request on the record with its status; a Pending
 * one can be withdrawn (ADR-0126). The event's details stay as they are (AC3). Every refusal is
 * the backend's, shown as it comes (AC6, AC7). The mock in src/mocks/handlers/changeRequests.ts
 * keeps the requests. Omar wrote EVR-7K2M9QXA "Partner Summit" (under review, coordinated by
 * Chloe: 12 Nov, 9:00 am to 5:00 pm, 250 expected); EVR-Q4ZT6N1B is a colleague's. The mock's
 * "now" is 5 Oct, 12:00 pm.
 */

const OMAR = MOCK_ACCOUNTS.organiser
const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
const COLLEAGUES_EVENT = 'EVR-Q4ZT6N1B'
const REASON = 'Speaker lands late.'
const REQUEST_A_CHANGE = 'Request a change'
const SEND = 'Send change request'
const WITHDRAW = 'Withdraw change request'
const REQUESTABLE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
  EVENT_REQUEST_STATUS.CONFIRMED,
]
/** Built from the statuses, so one added later is checked too. */
const NOT_REQUESTABLE_STATUSES = Object.values(EVENT_REQUEST_STATUS).filter(
  (status) => !REQUESTABLE_STATUSES.includes(status),
)
/** A request the coordinator has decided, which no longer offers a withdrawal (AC8). */
const APPROVED_REQUEST: ChangeRequest = {
  id: 41,
  status: 'approved',
  changes: [{ field: 'end_time', previous_value: '17:00:00', requested_value: '18:00:00' }],
  reason: 'Drinks after.',
  raised_by: 'Omar Rahman',
  raised_at: '2026-10-02T10:00:00+08:00',
  withdrawn_at: null,
  withdrawal_note: null,
}
/** A request the event's cancellation withdrew (AC9). */
const WITHDRAWN_ON_CANCEL: ChangeRequest = {
  ...APPROVED_REQUEST,
  id: 42,
  status: 'withdrawn',
  withdrawn_at: '2026-10-04T15:00:00+08:00',
  withdrawal_note: 'Withdrawn because the event was cancelled.',
}

function openAsOmar(reference: string) {
  return renderApp(organiserRequestPath(reference), { session: mockSessionFor(OMAR) })
}

/** The change request form, once the record has loaded. */
async function changeForm() {
  return within(await findRegion(REQUEST_A_CHANGE))
}

type User = ReturnType<typeof openAsOmar>['user']

/** On the open form: change the start to 10:00 and the attendance to 300, say why, and send. */
async function requestLaterStart(user: User) {
  const form = await changeForm()
  await user.clear(form.getByLabelText('Starts'))
  await user.type(form.getByLabelText('Starts'), '10:00')
  await user.clear(form.getByLabelText('Expected attendance'))
  await user.type(form.getByLabelText('Expected attendance'), '300')
  await user.type(form.getByLabelText('Why the change is needed'), REASON)
  await user.click(form.getByRole('button', { name: SEND }))
}

/** Omar's Partner Summit record as the mock sends it, with `changeRequests` on it. */
async function serveSummitWith(changeRequests: ChangeRequest[]) {
  sendRequestsAs(mockTokenFor(OMAR))
  const record = await fetchEventRequest(PARTNER_SUMMIT)
  server.use(
    http.get(`/api/events/requests/${PARTNER_SUMMIT}`, () =>
      HttpResponse.json({ ...record, change_requests: changeRequests }),
    ),
  )
}

describe('SCRUM-56 AC1, AC2, AC4 raising a change request', () => {
  it('sends what should change and why, and shows the request as Pending', async () => {
    const requests = recordRequests()
    const { user } = openAsOmar(PARTNER_SUMMIT)

    await requestLaterStart(user)

    const listed = await findRegion('Change requests')
    expect(await within(listed).findByText('Pending')).toBeInTheDocument()
    expect(listed).toHaveTextContent('Start time9:00 am → 10:00 am')
    expect(listed).toHaveTextContent('Expected attendance250 → 300')
    expect(listed).toHaveTextContent(REASON)
    expect(listed).toHaveTextContent('Raised by Omar Rahman, 5 Oct, 12:00 pm')
    const form = await changeForm()
    expect(form.getByText(/sent to the coordinator/)).toBeInTheDocument()
    expect(form.getByLabelText('Why the change is needed')).toHaveValue('')
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(new RegExp(`/api/events/requests/${PARTNER_SUMMIT}/change-requests$`))
    await expect(sent?.json()).resolves.toEqual({
      start_time: '10:00',
      expected_attendance: 300,
      reason: REASON,
    })
  })

  it("leaves the event's details as they were (AC3)", async () => {
    const { user } = openAsOmar(PARTNER_SUMMIT)

    await requestLaterStart(user)

    await within(await findRegion('Change requests')).findByText('Pending')
    expect(await findRegion('About the event')).toHaveTextContent('Expected attendance250')
    expect(statusShownFor(PARTNER_SUMMIT)).toBe('Under review')
  })

  it('opens the form with what the event holds now', async () => {
    openAsOmar(PARTNER_SUMMIT)

    const form = await changeForm()

    expect(form.getByLabelText('Date')).toHaveValue('2026-11-12')
    expect(form.getByLabelText('Starts')).toHaveValue('09:00')
    expect(form.getByLabelText('Expected attendance')).toHaveValue(250)
    expect(form.getByLabelText('Venue requirements')).toHaveValue(
      'A main hall for 250 and four breakout rooms.',
    )
    expect(form.getByLabelText('Programme notes')).toHaveValue(
      'Keynote at 9:30, breakout rooms after lunch.',
    )
    expect(form.getByLabelText('Why the change is needed')).toHaveValue('')
  })

  it.each(REQUESTABLE_STATUSES)('offers the form on a %s event', async (status) => {
    await serveRecordInStatus(OMAR, PARTNER_SUMMIT, status)
    openAsOmar(PARTNER_SUMMIT)

    expect(await findRegion(REQUEST_A_CHANGE)).toBeInTheDocument()
  })

  it.each(NOT_REQUESTABLE_STATUSES)('offers no form on a %s event (AC6)', async (status) => {
    await serveRecordInStatus(OMAR, PARTNER_SUMMIT, status)
    openAsOmar(PARTNER_SUMMIT)

    await findRegion('About the event')
    expect(screen.queryByRole('region', { name: REQUEST_A_CHANGE })).not.toBeInTheDocument()
  })

  it('offers the coordinator no form, but shows them the requests', async () => {
    await serveSummitWith([APPROVED_REQUEST])
    renderApp(coordinatorEventPath(PARTNER_SUMMIT), {
      session: mockSessionFor(MOCK_ACCOUNTS.coordinator),
    })

    const listed = await findRegion('Change requests')

    expect(listed).toHaveTextContent('Drinks after.')
    expect(screen.queryByRole('region', { name: REQUEST_A_CHANGE })).not.toBeInTheDocument()
  })
})

describe('SCRUM-56 AC6, AC7 the refusals, as the backend words them', () => {
  it("shows the backend's message under the box when no reason is given", async () => {
    const { user } = openAsOmar(PARTNER_SUMMIT)
    const form = await changeForm()

    await user.clear(form.getByLabelText('Ends'))
    await user.type(form.getByLabelText('Ends'), '18:00')
    await user.click(form.getByRole('button', { name: SEND }))

    expect(await form.findByText('Say why the change is needed.')).toBeInTheDocument()
    expect(form.getByLabelText('Why the change is needed')).toHaveFocus()
  })

  it("shows the backend's message when nothing would change", async () => {
    const { user } = openAsOmar(PARTNER_SUMMIT)
    const form = await changeForm()

    await user.type(form.getByLabelText('Why the change is needed'), REASON)
    await user.click(form.getByRole('button', { name: SEND }))

    expect(await form.findByRole('alert')).toHaveTextContent(
      "Say what should change: give at least one of the event's details a new value.",
    )
  })

  it("shows the backend's message on a colleague's event", async () => {
    const { user } = openAsOmar(COLLEAGUES_EVENT)

    await requestLaterStart(user)

    expect(await (await changeForm()).findByRole('alert')).toHaveTextContent(
      'Only the organiser who submitted this event can request a change to it or withdraw one.',
    )
  })

  it('says a request is already waiting for the coordinator when a second is sent (AC7)', async () => {
    const { user } = openAsOmar(PARTNER_SUMMIT)
    await requestLaterStart(user)
    await within(await findRegion('Change requests')).findByText('Pending')

    await requestLaterStart(user)

    expect(await (await changeForm()).findByRole('alert')).toHaveTextContent(
      'A change request is already waiting for the coordinator.',
    )
  })
})

describe('SCRUM-56 AC8, AC9 withdrawing a change request', () => {
  it('withdraws a Pending request, which then shows as Withdrawn with when', async () => {
    const { user } = openAsOmar(PARTNER_SUMMIT)
    await requestLaterStart(user)
    const listed = await findRegion('Change requests')
    const requests = recordRequests()

    await user.click(await within(listed).findByRole('button', { name: WITHDRAW }))

    expect(await within(listed).findByText('Withdrawn')).toBeInTheDocument()
    expect(listed).toHaveTextContent('Withdrawn 5 Oct, 12:00 pm')
    expect(within(listed).queryByRole('button', { name: WITHDRAW })).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(
      new RegExp(`/api/events/requests/${PARTNER_SUMMIT}/change-requests/\\d+/withdraw$`),
    )
  })

  it('offers no withdrawal of a request that is no longer Pending', async () => {
    await serveSummitWith([APPROVED_REQUEST])
    openAsOmar(PARTNER_SUMMIT)

    const listed = await findRegion('Change requests')

    expect(within(listed).getByText('Approved')).toBeInTheDocument()
    expect(within(listed).queryByRole('button', { name: WITHDRAW })).not.toBeInTheDocument()
  })

  it("shows the backend's refusal of a withdrawal", async () => {
    await serveSummitWith([{ ...APPROVED_REQUEST, status: 'pending' }])
    server.use(
      http.post(`/api/events/requests/${PARTNER_SUMMIT}/change-requests/41/withdraw`, () =>
        errorResponse(
          409,
          'change_request_not_pending',
          'Only a pending change request can be withdrawn; this one is approved.',
        ),
      ),
    )
    const { user } = openAsOmar(PARTNER_SUMMIT)
    const listed = await findRegion('Change requests')

    await user.click(within(listed).getByRole('button', { name: WITHDRAW }))

    expect(await within(listed).findByRole('alert')).toHaveTextContent(
      'Only a pending change request can be withdrawn; this one is approved.',
    )
  })

  it("shows why a request was withdrawn when the event's cancellation withdrew it", async () => {
    await serveSummitWith([WITHDRAWN_ON_CANCEL])
    openAsOmar(PARTNER_SUMMIT)

    const listed = await findRegion('Change requests')

    expect(listed).toHaveTextContent('Withdrawn because the event was cancelled.')
    expect(listed).toHaveTextContent('Withdrawn 4 Oct, 3:00 pm')
  })

  it('leaves the section out while the event has no change requests', async () => {
    openAsOmar(PARTNER_SUMMIT)

    await findRegion(REQUEST_A_CHANGE)
    expect(screen.queryByRole('region', { name: 'Change requests' })).not.toBeInTheDocument()
  })
})
