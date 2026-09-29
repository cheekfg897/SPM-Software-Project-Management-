import { connectApiClient } from '@/lib/api'

/**
 * Make apiRequest send `token`, or no token for null, in tests that call the API functions
 * without a store. Nothing is signed out on a 401. The unit tests' setup sends none again after
 * each test.
 */
export function sendRequestsAs(token: string | null): void {
  connectApiClient({ readAccessToken: () => token, handleUnauthorised: () => undefined })
}
