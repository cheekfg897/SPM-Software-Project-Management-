import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'

import { MOCK_ACCOUNTS, mockTokenFor } from '@/mocks/fixtures/accounts'
import { ApiError, fieldErrorsOf } from '@/lib/api'
import { recordRequests } from '@/test/recordRequests'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import {
  useActiveEvents,
  useAssignCoordinator,
  useCoordinatorWorkload,
  useReassignCoordinator,
  useUnassignedQueue,
} from './hooks'

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

/** The queue and the assign mutation sharing one query client, as the queue screen will. */
function renderQueueAndAssign() {
  return renderHook(() => ({ queue: useUnassignedQueue(), assign: useAssignCoordinator() }), {
    wrapper,
  })
}

/** Every Lead query and both actions on one query client, as moving between the two pages would. */
function renderEveryLeadHook() {
  return renderHook(
    () => ({
      queue: useUnassignedQueue(),
      active: useActiveEvents(),
      workload: useCoordinatorWorkload(),
      assign: useAssignCoordinator(),
      reassign: useReassignCoordinator(),
    }),
    { wrapper },
  )
}

/** How many times each Lead list was read, by its path. */
function readsOf(requests: Request[]) {
  const reads: Record<string, number> = {}
  for (const request of requests) {
    if (request.method === 'GET') {
      const path = new URL(request.url).pathname
      reads[path] = (reads[path] ?? 0) + 1
    }
  }
  return reads
}

/** Render every hook as the Lead and wait until each list has been read once. */
async function renderEveryLeadHookLoaded() {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))
  const requests = recordRequests()
  const rendered = renderEveryLeadHook()
  await waitFor(() => {
    expect(rendered.result.current.queue.isSuccess).toBe(true)
    expect(rendered.result.current.active.isSuccess).toBe(true)
    expect(rendered.result.current.workload.isSuccess).toBe(true)
  })
  return { ...rendered, requests }
}

const QUEUE_PATH = '/api/events/requests/unassigned'
const ACTIVE_PATH = '/api/events/requests/active'
const WORKLOAD_PATH = '/api/events/coordinators/workload'

describe('SCRUM-96 the Lead oversight hooks', () => {
  it('posts a reassignment by email, then reads the active list and the workload again, not the queue', async () => {
    const { result, requests } = await renderEveryLeadHookLoaded()

    result.current.reassign.mutate({
      reference: 'EVR-LEAD0003',
      coordinator_email: MOCK_ACCOUNTS.otherCoordinator.email,
    })

    await waitFor(() => expect(result.current.reassign.isSuccess).toBe(true))
    const post = requests.find((request) => request.method === 'POST')
    expect(new URL(post?.url ?? '').pathname).toBe('/api/events/requests/EVR-LEAD0003/reassign')
    expect(await post?.json()).toEqual({ coordinator_email: MOCK_ACCOUNTS.otherCoordinator.email })
    await waitFor(() =>
      expect(readsOf(requests)).toEqual({ [QUEUE_PATH]: 1, [ACTIVE_PATH]: 2, [WORKLOAD_PATH]: 2 }),
    )
    const moved = result.current.active.data?.event_requests.find(
      (row) => row.reference === 'EVR-LEAD0003',
    )
    expect(moved?.coordinator).toBe(MOCK_ACCOUNTS.otherCoordinator.full_name)
  })

  it('reads the queue, the active list and the workload again after an assignment from the queue', async () => {
    const { result, requests } = await renderEveryLeadHookLoaded()

    result.current.assign.mutate({
      reference: 'EVR-MOCK0001',
      coordinator_email: MOCK_ACCOUNTS.otherCoordinator.email,
    })

    await waitFor(() =>
      expect(readsOf(requests)).toEqual({ [QUEUE_PATH]: 2, [ACTIVE_PATH]: 2, [WORKLOAD_PATH]: 2 }),
    )
    const names = result.current.workload.data?.coordinators.map((entry) => entry.coordinator)
    expect(names).toEqual([
      MOCK_ACCOUNTS.otherCoordinator.full_name,
      MOCK_ACCOUNTS.coordinator.full_name,
    ])
    const heldByAisha = result.current.workload.data?.coordinators[0]?.event_requests ?? []
    expect(heldByAisha.map((row) => row.reference)).toContain('EVR-MOCK0001')
  })
})

describe('SCRUM-95 the Lead queue hooks', () => {
  it('returns the unassigned requests, oldest first, for the Lead', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))

    const { result } = renderQueueAndAssign()

    await waitFor(() => expect(result.current.queue.isSuccess).toBe(true))
    const rows = result.current.queue.data?.event_requests ?? []
    expect(rows.length).toBeGreaterThan(1)
    const submittedAt = rows.map((row) => row.submitted_at)
    expect(submittedAt).toEqual([...submittedAt].sort())
    expect(Object.keys(rows[0] ?? {}).sort()).toEqual([
      'end_time',
      'expected_attendance',
      'name',
      'proposed_date',
      'reference',
      'start_time',
      'submitted_at',
    ])
  })

  it('refuses an Event Coordinator the queue with a 403', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))

    const { result } = renderQueueAndAssign()

    await waitFor(() => expect(result.current.queue.isError).toBe(true))
    expect(result.current.queue.error).toBeInstanceOf(ApiError)
    expect((result.current.queue.error as ApiError).status).toBe(403) // -- narrowed by the line above
  })

  it('posts the coordinator by email, then reads the queue again without that request', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))
    const requests = recordRequests()
    const { result } = renderQueueAndAssign()
    await waitFor(() => expect(result.current.queue.isSuccess).toBe(true))
    const rows = result.current.queue.data?.event_requests ?? []
    const before = rows.length
    const queuedReference = rows[0]?.reference ?? ''
    expect(queuedReference).not.toBe('')

    result.current.assign.mutate({
      reference: queuedReference,
      coordinator_email: MOCK_ACCOUNTS.coordinator.email,
    })

    await waitFor(() => expect(result.current.assign.isSuccess).toBe(true))
    const post = requests.find((request) => request.method === 'POST')
    expect(new URL(post?.url ?? '').pathname).toBe(
      `/api/events/requests/${queuedReference}/coordinator`,
    )
    expect(await post?.json()).toEqual({ coordinator_email: MOCK_ACCOUNTS.coordinator.email })
    expect(result.current.assign.data?.coordinator.email).toBe(MOCK_ACCOUNTS.coordinator.email)
    await waitFor(() => expect(result.current.queue.data?.event_requests).toHaveLength(before - 1))
    const remaining = result.current.queue.data?.event_requests.map((row) => row.reference)
    expect(remaining).not.toContain(queuedReference)
  })

  it('surfaces an unknown email as a field error on coordinator_email', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))
    const { result } = renderQueueAndAssign()
    await waitFor(() => expect(result.current.queue.isSuccess).toBe(true))

    result.current.assign.mutate({
      reference: result.current.queue.data?.event_requests[0]?.reference ?? '',
      coordinator_email: 'nobody@example.com',
    })

    await waitFor(() => expect(result.current.assign.isError).toBe(true))
    expect(fieldErrorsOf(result.current.assign.error)).toEqual({
      coordinator_email: ['No Event Coordinator has this email address.'],
    })
  })

  it('answers a missing email with the payload 400 before it looks up the reference', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))
    const { result } = renderQueueAndAssign()

    // JSON.stringify drops an undefined value, so the body reaches the mock without the key.
    result.current.assign.mutate({
      reference: 'EVR-NOSUCH00',
      coordinator_email: undefined as unknown as string,
    })

    await waitFor(() => expect(result.current.assign.isError).toBe(true))
    expect((result.current.assign.error as ApiError).status).toBe(400) // -- the error is an ApiError, asserted in the 403 test
    expect(fieldErrorsOf(result.current.assign.error)).toEqual({
      coordinator_email: ['Missing data for required field.'],
    })
  })

  it('answers an unknown reference with 404 even when the email is also wrong', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))
    const { result } = renderQueueAndAssign()

    result.current.assign.mutate({
      reference: 'EVR-NOSUCH00',
      coordinator_email: 'nobody@example.com',
    })

    await waitFor(() => expect(result.current.assign.isError).toBe(true))
    expect((result.current.assign.error as ApiError).status).toBe(404) // -- the error is an ApiError, asserted in the 403 test
    expect(fieldErrorsOf(result.current.assign.error)).toEqual({})
  })

  it('answers a request that already left the queue with 409 even when the email is wrong', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))
    const { result } = renderQueueAndAssign()
    await waitFor(() => expect(result.current.queue.isSuccess).toBe(true))
    const reference = result.current.queue.data?.event_requests[0]?.reference ?? ''
    result.current.assign.mutate({
      reference,
      coordinator_email: MOCK_ACCOUNTS.coordinator.email,
    })
    await waitFor(() => expect(result.current.assign.isSuccess).toBe(true))

    result.current.assign.mutate({ reference, coordinator_email: 'nobody@example.com' })

    await waitFor(() => expect(result.current.assign.isError).toBe(true))
    expect((result.current.assign.error as ApiError).status).toBe(409) // -- the error is an ApiError, asserted in the 403 test
  })
})
