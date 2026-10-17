import { MOCK_ACCOUNTS } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'

/** Staff who may read the catalogue but not change it (SCRUM-27 AC3), named for `it.each`. */
export const OTHER_STAFF: [string, MockAccount][] = [
  ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
  ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
  ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
]
