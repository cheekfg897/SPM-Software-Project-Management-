import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { Provider } from 'react-redux'

import { MOCK_ACCOUNTS, mockSessionFor, mockTokenFor } from '@/mocks/fixtures/accounts'
import { recordRequests } from '@/test/recordRequests'
import { sendRequestsAs } from '@/test/sendRequestsAs'
import { createAppStore, signedIn } from '@/store'
import type { SignedInPayload } from '@/store'

import { fetchNotifications, fetchUnreadCount, markNotificationRead, notificationKeys } from './api'
import { useMarkRead, useNotifications, useUnreadCount } from './hooks'

function renderHookAs<T>(hook: () => T, session?: SignedInPayload) {
  const store = createAppStore()
  if (session) {
    store.dispatch(signedIn(session))
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </Provider>
    )
  }
  return { ...renderHook(hook, { wrapper: Wrapper }), store, queryClient }
}

const attendee = mockSessionFor(MOCK_ACCOUNTS.attendee)
const coordinator = mockSessionFor(MOCK_ACCOUNTS.coordinator)

describe('SCRUM-28 notifications hooks', () => {
  it('lists the signed-in viewer notifications, newest first', async () => {
    sendRequestsAs(attendee.accessToken)
    const { result } = renderHookAs(() => useNotifications(), attendee)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const times = result.current.data?.map((notification) => notification.created_at) ?? []
    expect(times.length).toBeGreaterThanOrEqual(3)
    expect([...times].sort().reverse()).toEqual(times)
  })

  it('returns the unread count the backend reports', async () => {
    sendRequestsAs(attendee.accessToken)
    const list = await fetchNotifications()
    const unreadInList = list.filter((notification) => notification.read_at === null).length
    const { result } = renderHookAs(() => useUnreadCount(), attendee)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toBe(unreadInList)
    expect(unreadInList).toBeGreaterThanOrEqual(2)
  })

  it('sends no request when nobody is signed in', async () => {
    const requests = recordRequests()
    const { result } = renderHookAs(() => ({
      list: useNotifications(),
      count: useUnreadCount(),
    }))

    await new Promise((resolve) => setTimeout(resolve, 20))

    expect(requests).toHaveLength(0)
    expect(result.current.list.fetchStatus).toBe('idle')
    expect(result.current.count.fetchStatus).toBe('idle')
  })

  it('keeps a separate cache entry for each viewer', async () => {
    sendRequestsAs(attendee.accessToken)
    const first = renderHookAs(() => useNotifications(), attendee)
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true))
    sendRequestsAs(coordinator.accessToken)
    const second = renderHookAs(() => useNotifications(), coordinator)
    await waitFor(() => expect(second.result.current.isSuccess).toBe(true))

    expect(notificationKeys.list(1)).not.toEqual(notificationKeys.list(3))
    expect(notificationKeys.unreadCount(1)).not.toEqual(notificationKeys.unreadCount(3))
    expect(first.result.current.data).not.toEqual(second.result.current.data)
  })

  it('reads again for the next viewer on the same query client', async () => {
    sendRequestsAs(attendee.accessToken)
    const { result, store } = renderHookAs(() => useNotifications(), attendee)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const attendeeRows = result.current.data

    sendRequestsAs(coordinator.accessToken)
    store.dispatch(signedIn(coordinator))
    await waitFor(() => expect(result.current.data).not.toEqual(attendeeRows))

    expect(result.current.data?.length).toBeGreaterThan(0)
  })
})

describe('SCRUM-28 marking read from a hook', () => {
  it('reads the list and the count again afterwards', async () => {
    sendRequestsAs(attendee.accessToken)
    const { result } = renderHookAs(
      () => ({ list: useNotifications(), count: useUnreadCount(), markRead: useMarkRead() }),
      attendee,
    )
    await waitFor(() => expect(result.current.count.data).toBe(2))
    const unread = result.current.list.data?.find((row) => row.read_at === null)

    await act(() => result.current.markRead.mutateAsync(unread?.id ?? 0))

    await waitFor(() => expect(result.current.count.data).toBe(1))
    const reread = result.current.list.data?.find((row) => row.id === unread?.id)
    expect(reread?.read_at).not.toBeNull()
  })
})

describe('SCRUM-28 notifications requests', () => {
  it('marks one read: the answer carries the time and the unread count drops', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.attendee))
    const before = await fetchUnreadCount()
    const unread = (await fetchNotifications()).find((row) => row.read_at === null)

    const requests = recordRequests()
    const marked = await markNotificationRead(unread?.id ?? 0)

    expect(marked.id).toBe(unread?.id)
    expect(marked.read_at).not.toBeNull()
    expect(requests[0]?.method).toBe('POST')
    expect(new URL(requests[0]?.url ?? '').pathname).toBe(`/api/notifications/${unread?.id}/read`)
    expect(await fetchUnreadCount()).toBe(before - 1)
  })
})
