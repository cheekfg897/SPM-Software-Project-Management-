import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { selectSessionUser, useAppSelector } from '@/store'

import { fetchNotifications, fetchUnreadCount, markNotificationRead, notificationKeys } from './api'

/** Who is signed in, for keying the queries. Null when nobody is, and the queries stay idle. */
function useViewerId(): number | null {
  return useAppSelector(selectSessionUser)?.id ?? null
}

/** The signed-in user's notifications, newest first. A visitor sends no request. */
export function useNotifications() {
  const viewerId = useViewerId()
  return useQuery({
    queryKey: notificationKeys.list(viewerId),
    queryFn: fetchNotifications,
    enabled: viewerId !== null,
  })
}

/** How many of the signed-in user's notifications are unread. A visitor sends no request. */
export function useUnreadCount() {
  const viewerId = useViewerId()
  return useQuery({
    queryKey: notificationKeys.unreadCount(viewerId),
    queryFn: fetchUnreadCount,
    enabled: viewerId !== null,
  })
}

/** Mark one notification read, then read both the list and the count again. */
export function useMarkRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  })
}
