import { ROLE } from '@/config/roles'
import { staffEventPath } from '@/config/routes'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EventListRow } from '../api'
import { useEventRequestsWithEquipment } from '../hooks'

import { RequestListSection } from './RequestListSection'

const TITLE = 'Events with equipment'

/**
 * Each row opens the event's read-only record, which links on to its Equipment page (ADR-0095).
 * SCRUM-38's queue still opens the Equipment page itself (ADR-0061).
 */
function pathFor(request: EventListRow): string {
  return staffEventPath(request.reference)
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
