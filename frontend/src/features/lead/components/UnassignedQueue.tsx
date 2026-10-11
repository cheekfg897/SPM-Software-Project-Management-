import { Button, ErrorAlert, Spinner } from '@/components/ui'

import { useUnassignedQueue } from '../hooks'

import { QueuedRequestCard } from './QueuedRequestCard'

/** The requests waiting for a coordinator, oldest first, or why there are none to show. */
export function UnassignedQueue() {
  const queue = useUnassignedQueue()

  if (queue.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-3">
        <Spinner />
        Loading unassigned requests…
      </p>
    )
  }
  if (queue.isError) {
    return (
      <div className="space-y-4">
        <ErrorAlert error={queue.error} />
        <Button variant="secondary" onClick={() => void queue.refetch()}>
          Try again
        </Button>
      </div>
    )
  }
  const { event_requests: requests, message } = queue.data
  if (requests.length === 0) {
    return (
      <p className="border-line text-ink-muted rounded-2xl border border-dashed px-6 py-16 text-center">
        {message}
      </p>
    )
  }
  return (
    <ul className="space-y-5">
      {requests.map((request) => (
        <li key={request.reference}>
          <QueuedRequestCard request={request} />
        </li>
      ))}
    </ul>
  )
}
