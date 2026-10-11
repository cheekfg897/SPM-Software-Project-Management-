import type { Page } from '@playwright/test'

import type { MockAccount } from '../src/mocks/fixtures/accounts'
import { mockSessionFor } from '../src/mocks/fixtures/accounts'

const SESSION_STORAGE_KEY = 'connectsphere.session'

/** Start the page already signed in as `account`, before any of the app's scripts run. */
export async function signInAs(page: Page, account: MockAccount) {
  const session = JSON.stringify(mockSessionFor(account))
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [
    SESSION_STORAGE_KEY,
    session,
  ] as const)
}
