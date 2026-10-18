import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { MOCK_ACCOUNTS } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'

/** The first mock account with `role`. */
function accountWith(role: Role): MockAccount {
  const account = Object.values(MOCK_ACCOUNTS).find((each) => each.role === role)
  if (account === undefined) {
    throw new Error(`No mock account has the role ${role}.`)
  }
  return account
}

/**
 * One account for every staff role but Venue Staff. Built from INTERNAL_ROLES, so a staff role
 * added later is checked too (the Safety Officer was missed once).
 */
export const OTHER_STAFF: readonly MockAccount[] = INTERNAL_ROLES.filter(
  (role) => role !== ROLE.VENUE_STAFF,
).map(accountWith)
