import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'

import type { EquipmentLineStatus } from './api'

/** Only Technical Support Staff reserve equipment (SCRUM-46); other staff just read. */
export const EQUIPMENT_RESERVER_ROLES: readonly Role[] = [ROLE.TECHNICAL_SUPPORT_STAFF]

/**
 * Each equipment line status in words, as the backend names it (EquipmentLineStatus, ADR-0077),
 * so the status never depends on colour to be read.
 */
export const EQUIPMENT_LINE_STATUS_LABELS: Record<EquipmentLineStatus, string> = {
  requested: 'Awaiting Technical Support',
  fulfilled: 'Fulfilled',
  partially_fulfilled: 'Partially fulfilled',
  unavailable: 'Unavailable',
}
