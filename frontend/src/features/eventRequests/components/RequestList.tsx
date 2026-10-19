import type { UseQueryResult } from '@tanstack/react-query'
import { Link } from 'react-router'

import { ErrorAlert, Spinner } from '@/components/ui'

import type { EventListRow, EventListRows } from '../api'

import { EventRequestRow } from './EventRequestRow'

export interface RequestListProps {
  /**
   * A role's list as its hook reads it. Every list has at least the list fields; an organiser's
   * and a coordinator's rows also carry the attendance, which the row shows when it is there.
   */
  requests: UseQueryResult<EventListRows>
  /** What the list is, for screen readers, e.g. "Your event requests". */
  label: string
  /** The page a row opens. Left out, the rows open nothing (Venue Staff's list, ADR-0090). */
  pathFor?: ((request: EventListRow) => string) | undefined
}

/** One row: a link to its page when the list has one for it, or just the row. */
function ListedRow({
  request,
  pathFor,
}: Pick<RequestListProps, 'pathFor'> & { request: EventListRow }) {
  if (pathFor === undefined) {
    return <EventRequestRow request={request} />
  }
  return (
    <Link
      to={pathFor(request)}
      className="focus-visible:outline-flare block rounded-2xl focus-visible:outline-2"
    >
      <EventRequestRow request={request} />
    </Link>
  )
}

/**
 * A role's event requests, in the order the backend sends them, each opening where `pathFor`
 * says, if anywhere. An empty list shows the backend's own message (SCRUM-24 AC8, AC11).
 */
export function RequestList({ requests, label, pathFor }: RequestListProps) {
  if (requests.isPending) {
    return (
      <p className="text-ink-muted mt-6 flex items-center gap-2">
        <Spinner /> Loading your events…
      </p>
    )
  }
  if (requests.isError) {
    return (
      <div className="mt-6">
        <ErrorAlert error={requests.error} />
      </div>
    )
  }

  const { event_requests: rows, message } = requests.data
  if (rows.length === 0) {
    return (
      <p className="border-line text-ink-muted mt-6 rounded-2xl border border-dashed px-6 py-12 text-center">
        {message}
      </p>
    )
  }
  return (
    <ul
      aria-label={label}
      className="border-line/50 bg-surface/40 mt-6 space-y-1 rounded-3xl border p-2"
    >
      {rows.map((request) => (
        <li key={request.reference}>
          <ListedRow request={request} pathFor={pathFor} />
        </li>
      ))}
    </ul>
  )
}
