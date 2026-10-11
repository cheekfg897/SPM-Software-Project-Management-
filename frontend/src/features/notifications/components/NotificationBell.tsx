import { Link } from 'react-router'

import { Badge } from '@/components/ui'
import { ROUTES } from '@/config/routes'
import { useUnreadCount } from '@/features/notifications/hooks'

/** A link to the notifications page that carries the unread count; no badge when there are none. */
export function NotificationBell() {
  const { data: unreadCount = 0 } = useUnreadCount()
  const hasUnread = unreadCount > 0
  const name = hasUnread ? `Notifications, ${unreadCount} unread` : 'Notifications'

  return (
    <Link
      to={ROUTES.NOTIFICATIONS}
      aria-label={name}
      className="text-ink-muted hover:text-ink -mx-1.5 -my-3 inline-flex items-center gap-1.5 p-3 transition"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="size-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7" />
        <path d="M10 20a2 2 0 0 0 4 0" />
      </svg>
      {hasUnread && <Badge>{unreadCount}</Badge>}
    </Link>
  )
}
