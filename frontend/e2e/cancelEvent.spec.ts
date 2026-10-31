import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/**
 * SCRUM-61: an Event Organiser cancels their confirmed event from its page (ADR-0122). They type
 * why, are asked first (it can't be undone, what is released, how many registered attendees are
 * told), and say yes; the page shows the event Cancelled, offers nothing more, and its history
 * keeps the reason. Against the mock backend, which keeps its data only until the page reloads.
 */

const REASON = 'Our keynote speaker has withdrawn.'

test('SCRUM-61: an organiser cancels their confirmed event, saying why', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.otherOrganiser)
  await page.goto('/organiser')
  const list = page.getByRole('list', { name: 'Your event requests' })
  await list.getByRole('link', { name: /Year-End Town Hall/ }).click()
  await expect(page).toHaveURL('/organiser/requests/EVR-BOOK0102')

  // --- The reason, then the second question before anything is sent ---
  const card = page.getByRole('region', { name: 'Cancel the event' })
  await card.getByLabel('Reason for cancelling').fill(REASON)
  await card.getByRole('button', { name: 'Cancel event' }).click()
  await expect(card).toContainText("This can't be undone.")
  await expect(card).toContainText('3 registered attendees are told.')

  // --- Yes: the event is Cancelled, nothing is left to cancel, the history says why ---
  await card.getByRole('button', { name: 'Yes, cancel the event' }).click()
  const status = page
    .getByText('EVR-BOOK0102', { exact: true })
    .locator('xpath=preceding-sibling::*[1]')
  await expect(status).toHaveText('Cancelled')
  await expect(page.getByRole('region', { name: 'Cancel the event' })).toHaveCount(0)
  const history = page.getByRole('region', { name: 'History' })
  await expect(history).toContainText('Event cancelled')
  await expect(history).toContainText(REASON)
})
