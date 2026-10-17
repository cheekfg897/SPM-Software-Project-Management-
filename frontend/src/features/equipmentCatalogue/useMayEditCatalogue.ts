import { selectSessionUser, useAppSelector } from '@/store'

import { EQUIPMENT_CATALOGUE_EDITOR_ROLES } from './constants'

/**
 * Whether the signed-in user may add and change equipment types, so the links to do it are shown
 * only to them (SCRUM-27 AC3). The backend still refuses anyone else.
 */
export function useMayEditCatalogue(): boolean {
  const user = useAppSelector(selectSessionUser)
  return user !== null && EQUIPMENT_CATALOGUE_EDITOR_ROLES.includes(user.role)
}
