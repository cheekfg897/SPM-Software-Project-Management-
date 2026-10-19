import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'

import type { OutOfServiceReason } from './api'

/** Only Technical Support Staff add and change equipment types (SCRUM-27 AC3); other staff read. */
export const EQUIPMENT_CATALOGUE_EDITOR_ROLES: readonly Role[] = [ROLE.TECHNICAL_SUPPORT_STAFF]

/** Each reason for units being out of service, as Jira's AC1 names it (SCRUM-47). */
export const OUT_OF_SERVICE_REASON_LABELS: Record<OutOfServiceReason, string> = {
  damaged: 'Damaged',
  under_maintenance: 'Under maintenance',
}
