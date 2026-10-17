import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'

/** Only Technical Support Staff add and change equipment types (SCRUM-27 AC3); other staff read. */
export const EQUIPMENT_CATALOGUE_EDITOR_ROLES: readonly Role[] = [ROLE.TECHNICAL_SUPPORT_STAFF]
