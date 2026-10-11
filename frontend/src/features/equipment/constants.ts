import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'

/** Only Technical Support Staff reserve equipment (SCRUM-46); other staff just read. */
export const EQUIPMENT_RESERVER_ROLES: readonly Role[] = [ROLE.TECHNICAL_SUPPORT_STAFF]
