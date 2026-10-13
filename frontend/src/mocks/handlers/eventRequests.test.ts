import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

/**
 * The mock of GET /api/events/requests, pinned to what the backend sends an Event Organiser
 * (SCRUM-7, SCRUM-20 AC4, SCRUM-24 AC10, ADR-0020). The integration tests check the same shape
 * against the running backend.
 */

const MY_REQUESTS = '/api/events/requests'

interface ListedRequest {
  reference: string
  status: string
  proposed_date: string | null
}

interface RequestList {
  event_requests: ListedRequest[]
  message?: string
}

function fetchAs(account: MockAccount | null) {
  sendRequestsAs(account === null ? null : mockTokenFor(account))
  return apiRequest<RequestList>(MY_REQUESTS)
}

describe('SCRUM-7 mock of an organiser event requests', () => {
  it("lists the organisation's requests and the organiser's own drafts, newest request first", async () => {
    const list = await fetchAs(MOCK_ACCOUNTS.organiser)

    // A colleague's draft and another organisation's request are the newest in the mock,
    // so leaking either would put it first.
    expect(list.event_requests.map((row) => row.reference)).toEqual([
      'EVR-7K2M9QXA',
      'EVR-3HD8PL2W',
      'EVR-Q4ZT6N1B',
      'EVR-W9CR5E7M',
      'EVR-B6YF2K8V',
      'EVR-M1XJ7T3D',
    ])
    expect(list).not.toHaveProperty('message')
  })

  it('shows a draft with its details still empty, and no internal ids', async () => {
    const list = await fetchAs(MOCK_ACCOUNTS.organiser)

    const draft = list.event_requests.find((row) => row.reference === 'EVR-3HD8PL2W')
    expect(draft).toMatchObject({ status: 'draft', proposed_date: null })
    expect(draft).not.toHaveProperty('organiser_id')
    expect(draft).not.toHaveProperty('organisation_id')
  })

  it('gives an organisation with no requests an empty list and the backend message', async () => {
    const newcomer = await apiRequest<{ id: number }>('/api/auth/register', {
      method: 'POST',
      body: {
        full_name: 'Nina Organiser',
        email: 'nina@example.com',
        password: MOCK_ACCOUNTS.organiser.password,
        role: 'event_organiser',
        organisation_id: 3,
      },
    })

    const list = await fetchAs({ ...MOCK_ACCOUNTS.organiser, id: newcomer.id, organisation_id: 3 })

    expect(list).toEqual({
      event_requests: [],
      message: 'Your organisation has no event requests yet.',
    })
  })

  it('refuses an organiser whose account has no organisation', async () => {
    await expect(fetchAs(MOCK_ACCOUNTS.unlinkedOrganiser)).rejects.toMatchObject({
      status: 403,
      code: 'organiser_without_organisation',
      message: 'Your account is not linked to a client organisation yet.',
    })
  })

  it.each([MOCK_ACCOUNTS.attendee, MOCK_ACCOUNTS.coordinator])(
    'refuses anyone who is not an Event Organiser ($role)',
    async (account) => {
      await expect(fetchAs(account)).rejects.toMatchObject({
        status: 403,
        code: 'authorization_error',
        message: 'You do not have permission to perform this action.',
      })
    },
  )

  it('refuses a request with no token', async () => {
    await expect(fetchAs(null)).rejects.toMatchObject({
      status: 401,
      code: 'authentication_error',
    })
  })
})
