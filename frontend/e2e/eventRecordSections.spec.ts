import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'

/**
 * SCRUM-33 AC5 and SCRUM-55: a coordinator opens one of their events and reads what has happened
 * to it and who has registered (ADR-0076). Against the mock backend.
 */

test('SCRUM-33, SCRUM-55: a coordinator opens an event and sees its history and registrants', async ({
  page,
}) => {
  await page.goto('/staff/login')
  await logIn(page, MOCK_ACCOUNTS.coordinator)
  await expect(page).toHaveURL('/staff')

  const assigned = page.getByRole('list', { name: 'Your assigned events' })
  await assigned.getByRole('link', { name: /Year-End Town Hall/ }).click()

  await expect(page).toHaveURL('/events/EVR-BOOK0102')
  const history = page.getByRole('region', { name: 'History' })
  const entries = history.getByRole('listitem')
  // In mock mode the history arrives after the record: wait for its first entry.
  await expect(entries.first()).toContainText('Coordinator assigned')
  await expect(entries).toHaveCount(10)
  await expect(entries.nth(2)).toContainText('Request approved')
  await expect(entries.nth(9)).toContainText('Registration capacity changed')
  await expect(entries.nth(9)).toContainText('5 Oct, 10:30 am · Chloe Lim')

  const registrants = page.getByRole('region', { name: 'Registrants' })
  await expect(registrants.getByText('3 registered of 80 places · 77 left')).toBeVisible()
  const rows = registrants.getByRole('row')
  await expect(rows).toHaveCount(4)
  await expect(rows.nth(1)).toContainText('Hannah Lee')
  await expect(rows.nth(1)).toContainText('hannah.lee@example.com')
})
