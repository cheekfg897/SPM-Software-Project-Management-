import { useId } from 'react'

import { ROLE } from '@/config/roles'
import { coordinatorEventPath } from '@/config/routes'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EventRequest } from '../api'
import { useAssignedEventRequests } from '../hooks'

import { RequestList } from './RequestList'

const TITLE = 'Your assigned events'

/** A coordinator opens an event's record at their own address (ADR-0046). */
function pathFor(request: EventRequest): string {
  return coordinatorEventPath(request.reference)
}

function AssignedList() {
  const requests = useAssignedEventRequests()
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="mt-12">
      <h2 id={headingId} className="font-display text-2xl font-semibold tracking-tight">
        {TITLE}
      </h2>
      <RequestList requests={requests} label={TITLE} pathFor={pathFor} />
    </section>
  )
}

/**
 * On Staff home, an Event Coordinator's assigned events, newest first, each opening its record
 * (SCRUM-24 AC2, AC9, AC11; ADR-0046). Other staff roles' lists come later, so they see none
 * and nothing is asked for.
 */
export function AssignedEventRequests() {
  const viewer = useAppSelector(selectSessionUser)
  if (viewer?.role !== ROLE.EVENT_COORDINATOR) {
    return null
  }
  return <AssignedList />
}
