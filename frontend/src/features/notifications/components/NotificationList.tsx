import { Link } from 'react-router'

import { Badge, Button, ErrorAlert } from '@/components/ui'
import { formatDateTime } from '@/lib/formatDate'

import type { Notification } from '../api'
import { useMarkRead } from '../hooks'

function NotificationRow({ notification }: { notification: Notification }) {
  const markRead = useMarkRead()
  const isUnread = notification.read_at === null

  return (
    <li
      className={`rounded-2xl border p-5 ${
        isUnread ? 'border-flare/40 bg-surface-raised' : 'border-line/70 bg-surface/70'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className={isUnread ? 'text-ink font-medium' : 'text-ink-muted'}>
          {notification.message}
        </p>
        {isUnread && <Badge>Unread</Badge>}
      </div>
      <p className="text-ink-muted mt-2 text-sm">
        <Link to={notification.link} className="text-flare hover:underline">
          {notification.event_name}
        </Link>
      </p>
      <p className="text-ink-faint mt-1 text-sm">
        <time dateTime={notification.created_at}>{formatDateTime(notification.created_at)}</time>
      </p>
      {notification.detail !== null && (
        <p className="text-ink-muted mt-2 text-sm">{notification.detail}</p>
      )}
      {isUnread && (
        <div className="mt-4 space-y-3">
          <ErrorAlert error={markRead.error} />
          <Button
            variant="secondary"
            isPending={markRead.isPending}
            onClick={() => markRead.mutate(notification.id)}
          >
            Mark read
          </Button>
        </div>
      )}
    </li>
  )
}

/** The notifications in the order the backend sent them. */
export function NotificationList({ notifications }: { notifications: Notification[] }) {
  return (
    <ul className="space-y-4">
      {notifications.map((notification) => (
        <NotificationRow key={notification.id} notification={notification} />
      ))}
    </ul>
  )
}
