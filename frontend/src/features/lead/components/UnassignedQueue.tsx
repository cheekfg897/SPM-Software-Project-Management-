import { useState } from 'react'

import { EmptyState, ErrorAlert } from '@/components/ui'

import type { UnassignedQueue as QueueBody, UnassignedRequest } from '../api'
import { useUnassignedQueue } from '../hooks'

import { QueryResult } from './QueryResult'
import { QueuedRequestCard } from './QueuedRequestCard'

/** The Lead's latest refused assignment: which request, and the backend's error. */
interface Refusal {
  request: UnassignedRequest
  error: Error
}

interface QueueListProps extends QueueBody {
  refusal: Refusal | null
  onAssigned: () => void
  onRefused: (refusal: Refusal) => void
}

/**
 * The backend's refusal for a request that has since left the queue, e.g. because another Lead
 * assigned it first (SCRUM-95 AC4). While the request is still queued its own card says why, so
 * nothing is shown here.
 */
function RefusalForALeftRequest({
  refusal,
  requests,
}: {
  refusal: Refusal | null
  requests: UnassignedRequest[]
}) {
  if (refusal === null) {
    return null
  }
  const { reference, name } = refusal.request
  const stillQueued = requests.some((request) => request.reference === reference)
  if (stillQueued) {
    return null
  }
  return <ErrorAlert title={`${name} (${reference})`} error={refusal.error} />
}

function QueueList({
  event_requests: requests,
  message,
  refusal,
  onAssigned,
  onRefused,
}: QueueListProps) {
  return (
    <div className="space-y-5">
      <RefusalForALeftRequest refusal={refusal} requests={requests} />
      {/* The backend sends a message only with an empty queue (SCRUM-24 AC11, ADR-0036). */}
      {message !== undefined ? (
        <EmptyState message={message} />
      ) : (
        <ul className="space-y-5">
          {requests.map((request) => (
            <li key={request.reference}>
              <QueuedRequestCard
                request={request}
                onAssigned={onAssigned}
                onRefused={(error) => onRefused({ request, error })}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** The requests waiting for a coordinator, oldest first, or why there are none to show. */
export function UnassignedQueue() {
  const queue = useUnassignedQueue()
  const [refusal, setRefusal] = useState<Refusal | null>(null)

  return (
    <QueryResult query={queue} loadingLabel="Loading unassigned requests…">
      {(body) => (
        <QueueList
          {...body}
          refusal={refusal}
          onAssigned={() => setRefusal(null)}
          onRefused={setRefusal}
        />
      )}
    </QueryResult>
  )
}
