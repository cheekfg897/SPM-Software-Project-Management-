import { PageContainer } from '@/components/layout'
import { EmptyState, ErrorAlert, Spinner } from '@/components/ui'

import { NotificationList } from '../components/NotificationList'
import { useNotifications } from '../hooks'

function NotificationsBody() {
  const notifications = useNotifications()

  if (notifications.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-2">
        <Spinner />
        Loading notifications…
      </p>
    )
  }
  if (notifications.isError) {
    return <ErrorAlert error={notifications.error} />
  }
  if (notifications.data.length === 0) {
    return <EmptyState message="You have no notifications yet." />
  }
  return <NotificationList notifications={notifications.data} />
}

/** The signed-in user's notifications (SCRUM-28), newest first, as the backend sends them. */
export function NotificationsPage() {
  return (
    <PageContainer title="Notifications">
      <div className="mt-10">
        <NotificationsBody />
      </div>
    </PageContainer>
  )
}
