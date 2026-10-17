import { ROLE } from '@/config/roles'
import { eventEquipmentPath } from '@/config/routes'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EventListRow } from '../api'
import { useEventRequestsWithEquipment } from '../hooks'

import { RequestListSection } from './RequestListSection'

const TITLE = 'Events with equipment'

/** Technical Support can't open an event's record, but may open its Equipment page (ADR-0061). */
function pathFor(request: EventListRow): string {
  return eventEquipmentPath(request.reference)
}

function EquipmentList() {
  const requests = useEventRequestsWithEquipment()
  return <RequestListSection title={TITLE} requests={requests} pathFor={pathFor} />
}

/**
 * On Staff home, every event with an equipment request, newest first, for Technical Support
 * (SCRUM-24 AC5, AC8, AC11; ADR-0061). Other roles see none, and nothing is asked for.
 */
export function EquipmentEventRequests() {
  const viewer = useAppSelector(selectSessionUser)
  if (viewer?.role !== ROLE.TECHNICAL_SUPPORT_STAFF) {
    return null
  }
  return <EquipmentList />
}
