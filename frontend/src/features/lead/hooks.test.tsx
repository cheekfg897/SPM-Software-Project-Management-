import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'

import { MOCK_ACCOUNTS, mockTokenFor } from '@/mocks/fixtures/accounts'
import { ApiError, fieldErrorsOf } from '@/lib/api'
import { recordRequests } from '@/test/recordRequests'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { useAssignCoordinator, useUnassignedQueue } from './hooks'

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
