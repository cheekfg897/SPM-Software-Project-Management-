import { apiRequest } from '@/lib/api'

/** The notifications API: backend/app/modules/notifications/routes.py. */
const NOTIFICATION_PATHS = {
  LIST: '/api/notifications',
  UNREAD_COUNT: '/api/notifications/unread-count',
} as const

export interface Notification {
  id: number
  kind: string
  /** What happened, in words. Shown as sent. */
  message: string
  event_reference: string
  event_name: string
  /** Where to open the event. Used as sent. */
  link: string
  /** ISO date-time with an offset, in business time. */
  created_at: string
  /** When it was read; null while unread. */
  read_at: string | null
  detail: string | null
}

export const notificationKeys = {
  all: ['notifications'] as const,
  /** One viewer's list: signing in as someone else reads it again instead of showing the last viewer's. */
  list: (viewerId: number | null) => [...notificationKeys.all, 'list', viewerId] as const,
  unreadCount: (viewerId: number | null) =>
    [...notificationKeys.all, 'unread-count', viewerId] as const,
}

/** The signed-in user's notifications, newest first. */
export async function fetchNotifications(): Promise<Notification[]> {
  const body = await apiRequest<{ notifications: Notification[] }>(NOTIFICATION_PATHS.LIST)
  return body.notifications
}

export async function fetchUnreadCount(): Promise<number> {
  const body = await apiRequest<{ unread_count: number }>(NOTIFICATION_PATHS.UNREAD_COUNT)
  return body.unread_count
}

/** Mark one notification read. Marking a read one again keeps its first read time. */
export function markNotificationRead(id: number): Promise<Notification> {
  return apiRequest<Notification>(`${NOTIFICATION_PATHS.LIST}/${id}/read`, { method: 'POST' })
}
