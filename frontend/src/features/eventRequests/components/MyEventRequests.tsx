import { ButtonLink } from '@/components/ui'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import { editDraftPath, organiserRequestPath, ROUTES } from '@/config/routes'

import type { EventListRow } from '../api'
import { useMyEventRequests } from '../hooks'

import { RequestList } from './RequestList'

/** Where a row opens: the organiser's own draft for editing (SCRUM-20 AC3), else the record. */
function pathFor(request: EventListRow): string {
  if (request.status === EVENT_REQUEST_STATUS.DRAFT) {
    return editDraftPath(request.reference)
  }
  return organiserRequestPath(request.reference)
}

/**
 * The organiser's client organisation's event requests, newest first, with a way to start a new
 * one above them (SCRUM-19, SCRUM-24 AC1, AC9).
 */
export function MyEventRequests() {
  const requests = useMyEventRequests()
  return (
    <>
      <div className="mt-10 flex justify-end">
        <ButtonLink to={ROUTES.NEW_EVENT_REQUEST}>New event request</ButtonLink>
      </div>
      <RequestList requests={requests} label="Your event requests" pathFor={pathFor} />
    </>
  )
}
