import { ROLE } from '@/config/roles'
import { coordinatorEventPath } from '@/config/routes'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EventListRow } from '../api'
import { useAssignedEventRequests } from '../hooks'

import { RequestListSection } from './RequestListSection'

const TITLE = 'Your assigned events'

/** A coordinator opens an event's record at their own address (ADR-0056). */
function pathFor(request: EventListRow): string {
  return coordinatorEventPath(request.reference)
}

function AssignedList() {
  const requests = useAssignedEventRequests()
  return <RequestListSection title={TITLE} requests={requests} pathFor={pathFor} />
}

/**
 * On Staff home, an Event Coordinator's assigned events, newest first, each opening its record
 * (SCRUM-24 AC2, AC9, AC11; ADR-0056). Other staff roles' lists come later, so they see none
 * and nothing is asked for.
 */
export function AssignedEventRequests() {
  const viewer = useAppSelector(selectSessionUser)
  if (viewer?.role !== ROLE.EVENT_COORDINATOR) {
    return null
  }
  return <AssignedList />
}
