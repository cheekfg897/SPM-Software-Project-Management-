import { Link } from 'react-router'

import { ButtonLink, ErrorAlert, Spinner } from '@/components/ui'
import { editDraftPath, organiserRequestPath, ROUTES } from '@/config/routes'

import type { EventRequest } from '../api'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'

import { useMyEventRequests } from '../hooks'

import { EventRequestRow } from './EventRequestRow'

/** Where a row opens: the organiser's own draft for editing (SCRUM-20 AC3), else the record. */
function pathFor(request: EventRequest): string {
  if (request.status === EVENT_REQUEST_STATUS.DRAFT) {
    return editDraftPath(request.reference)
  }
  return organiserRequestPath(request.reference)
}

/** One row of the list, opening its draft or its record (SCRUM-24 AC9, ADR-0046). */
function ListedRequest({ request }: { request: EventRequest }) {
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
 * The organiser's client organisation's event requests, in the order the backend sends them
 * (newest request first). An empty list shows the backend's own message (SCRUM-24 AC11).
 */
function RequestList() {
  const requests = useMyEventRequests()

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
      aria-label="Your event requests"
      className="border-line/50 bg-surface/40 mt-6 space-y-1 rounded-3xl border p-2"
    >
      {rows.map((request) => (
        <li key={request.reference}>
          <ListedRequest request={request} />
        </li>
      ))}
    </ul>
  )
}

/** The organiser's requests, with a way to start a new one above them (SCRUM-19). */
export function MyEventRequests() {
  return (
    <>
      <div className="mt-10 flex justify-end">
        <ButtonLink to={ROUTES.NEW_EVENT_REQUEST}>New event request</ButtonLink>
      </div>
      <RequestList />
    </>
  )
}
