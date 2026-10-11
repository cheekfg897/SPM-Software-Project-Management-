import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'

import { MOCK_ACCOUNTS, mockTokenFor } from '@/mocks/fixtures/accounts'
import { ApiError, fieldErrorsOf } from '@/lib/api'
import { recordRequests } from '@/test/recordRequests'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { useAssignCoordinator, useUnassignedQueue } from './hooks'

const FIRST_REFERENCE = 'ER-0001'

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
    const before = result.current.queue.data?.event_requests.length ?? 0

    result.current.assign.mutate({
      reference: FIRST_REFERENCE,
      coordinator_email: MOCK_ACCOUNTS.coordinator.email,
    })

    await waitFor(() => expect(result.current.assign.isSuccess).toBe(true))
    const post = requests.find((request) => request.method === 'POST')
    expect(new URL(post?.url ?? '').pathname).toBe(
      `/api/events/requests/${FIRST_REFERENCE}/coordinator`,
    )
    expect(await post?.json()).toEqual({ coordinator_email: MOCK_ACCOUNTS.coordinator.email })
    expect(result.current.assign.data?.coordinator.email).toBe(MOCK_ACCOUNTS.coordinator.email)
    await waitFor(() => expect(result.current.queue.data?.event_requests).toHaveLength(before - 1))
  })

  it('surfaces an unknown email as a field error on coordinator_email', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.lead))
    const { result } = renderQueueAndAssign()

    result.current.assign.mutate({
      reference: FIRST_REFERENCE,
      coordinator_email: 'nobody@example.com',
    })

    await waitFor(() => expect(result.current.assign.isError).toBe(true))
    expect(fieldErrorsOf(result.current.assign.error)).toEqual({
      coordinator_email: ['No Event Coordinator has this email address.'],
    })
  })
})
