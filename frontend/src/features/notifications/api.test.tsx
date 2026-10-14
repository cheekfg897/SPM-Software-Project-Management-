import { act, waitFor } from '@testing-library/react'

import { MOCK_ACCOUNTS, mockSessionFor, mockTokenFor } from '@/mocks/fixtures/accounts'
import { recordRequests } from '@/test/recordRequests'
import { renderHookWithProviders } from '@/test/render'
import { sendRequestsAs } from '@/test/sendRequestsAs'
import { signedIn } from '@/store'

import { fetchNotifications, fetchUnreadCount, markNotificationRead } from './api'
import { useMarkRead, useNotifications, useUnreadCount } from './hooks'

const attendee = mockSessionFor(MOCK_ACCOUNTS.attendee)
const coordinator = mockSessionFor(MOCK_ACCOUNTS.coordinator)

describe('SCRUM-28 notifications hooks', () => {
  it('lists the signed-in viewer notifications, newest first', async () => {
    sendRequestsAs(attendee.accessToken)
    const { result } = renderHookWithProviders(() => useNotifications(), { session: attendee })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const times = result.current.data?.map((notification) => notification.created_at) ?? []
    expect(times.length).toBeGreaterThanOrEqual(3)
    expect([...times].sort().reverse()).toEqual(times)
  })

  it('returns the unread count the backend reports', async () => {
    sendRequestsAs(attendee.accessToken)
    const list = await fetchNotifications()
    const unreadInList = list.filter((notification) => notification.read_at === null).length
    const { result } = renderHookWithProviders(() => useUnreadCount(), { session: attendee })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toBe(unreadInList)
    expect(unreadInList).toBeGreaterThanOrEqual(2)
  })

  it('sends no request when nobody is signed in', async () => {
    const requests = recordRequests()
    const { result } = renderHookWithProviders(() => ({
      list: useNotifications(),
      count: useUnreadCount(),
    }))

    await new Promise((resolve) => setTimeout(resolve, 20))

    expect(requests).toHaveLength(0)
    expect(result.current.list.fetchStatus).toBe('idle')
    expect(result.current.count.fetchStatus).toBe('idle')
  })

  it('reads again for the next viewer on the same query client', async () => {
    sendRequestsAs(attendee.accessToken)
    const { result, store } = renderHookWithProviders(() => useNotifications(), {
      session: attendee,
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const attendeeRows = result.current.data

    sendRequestsAs(coordinator.accessToken)
    store.dispatch(signedIn(coordinator))
    await waitFor(() => expect(result.current.data).not.toEqual(attendeeRows))

    expect(result.current.data?.length).toBeGreaterThan(0)
  })

  it('asks for the next viewer unread count on the same query client', async () => {
    sendRequestsAs(attendee.accessToken)
    const { result, store } = renderHookWithProviders(() => useUnreadCount(), {
      session: attendee,
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    // Every mock account has two unread, so the count alone can't show whose it is.
    const requests = recordRequests()

    sendRequestsAs(coordinator.accessToken)
    store.dispatch(signedIn(coordinator))

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(new URL(requests[0]?.url ?? '').pathname).toBe('/api/notifications/unread-count')
  })
})

describe('SCRUM-28 marking read from a hook', () => {
  it('reads the list and the count again afterwards', async () => {
    sendRequestsAs(attendee.accessToken)
    const { result } = renderHookWithProviders(
      () => ({ list: useNotifications(), count: useUnreadCount(), markRead: useMarkRead() }),
      { session: attendee },
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
