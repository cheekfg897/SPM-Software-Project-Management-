import { EmptyState } from '@/components/ui'

import type { UnassignedQueue as QueueBody } from '../api'
import { useUnassignedQueue } from '../hooks'

import { QueryResult } from './QueryResult'
import { QueuedRequestCard } from './QueuedRequestCard'

function QueueList({ event_requests: requests, message }: QueueBody) {
  // The backend sends a message only with an empty queue (SCRUM-24 AC11, ADR-0036).
  if (message !== undefined) {
    return <EmptyState message={message} />
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

/** The requests waiting for a coordinator, oldest first, or why there are none to show. */
export function UnassignedQueue() {
  const queue = useUnassignedQueue()

  return (
    <QueryResult query={queue} loadingLabel="Loading unassigned requests…">
      {(body) => <QueueList {...body} />}
    </QueryResult>
  )
}
