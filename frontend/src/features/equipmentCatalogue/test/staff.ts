import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { MOCK_ACCOUNTS } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'

/** The mock account a test signs in as to act with `role`. */
function accountWithRole(role: Role): MockAccount {
  const account = Object.values(MOCK_ACCOUNTS).find((candidate) => candidate.role === role)
  if (account === undefined) {
    throw new Error(`No mock account has the role ${role}.`)
  }
  return account
}

/**
 * Staff who may read the catalogue but not change it (SCRUM-27 AC3), named by role for `it.each`.
 * Every internal role but Technical Support, so a staff role added later is checked too.
 */
export const OTHER_STAFF: [string, MockAccount][] = INTERNAL_ROLES.filter(
  (role) => role !== ROLE.TECHNICAL_SUPPORT_STAFF,
).map((role) => [role, accountWithRole(role)])
