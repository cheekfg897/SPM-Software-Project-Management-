import { ErrorAlert, Spinner } from '@/components/ui'

import { useMyEventRequests } from '../hooks'

import { EventRequestRow } from './EventRequestRow'

/**
 * The organiser's client organisation's event requests, in the order the backend sends them
 * (newest request first). An empty list shows the backend's own message (SCRUM-24 AC10).
 */
export function MyEventRequests() {
  const requests = useMyEventRequests()

  if (requests.isPending) {
    return (
      <p className="text-ink-muted mt-10 flex items-center gap-2">
        <Spinner /> Loading your events…
      </p>
    )
  }
  if (requests.isError) {
    return (
      <div className="mt-10">
        <ErrorAlert error={requests.error} />
      </div>
    )
  }

  const { event_requests: rows, message } = requests.data
  if (rows.length === 0) {
    return (
      <p className="border-line text-ink-muted mt-10 rounded-2xl border border-dashed px-6 py-12 text-center">
        {message}
      </p>
    )
  }
  return (
    <ul
      aria-label="Your event requests"
      className="border-line/50 bg-surface/40 mt-10 space-y-1 rounded-3xl border p-2"
    >
      {rows.map((request) => (
        <li key={request.reference}>
          <EventRequestRow request={request} />
        </li>
      ))}
    </ul>
  )
}
