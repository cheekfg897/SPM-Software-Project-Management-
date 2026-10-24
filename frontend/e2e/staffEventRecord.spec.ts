import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'
import { signInAs } from './signInAs'

/**
 * SCRUM-24 AC9, AC10; SCRUM-84 AC2, SCRUM-33 AC5: staff who aren't the event's coordinator open
 * its read-only record from their own lists, and see its preparation and history, with nothing
 * to change (ADR-0095). Against the mock backend.
 */

test('SCRUM-24 AC9: Venue Staff open an event from their list and see its venue preparation', async ({
  page,
}) => {
  await page.goto('/staff/login')
  await logIn(page, MOCK_ACCOUNTS.venueStaff)
  await expect(page).toHaveURL('/staff')

  await page
    .getByRole('list', { name: 'Events with venue bookings' })
    .getByRole('link', { name: /EVR-BOOK0110/ })
    .click()

  await expect(page).toHaveURL('/staff/events/EVR-BOOK0110')
  const venues = page.getByRole('region', { name: 'Venue arrangements' })
  await expect(venues).toContainText('Marina Hall')
  await expect(venues).toContainText('Preparation: In progress')
  await expect(venues).toContainText('Preparation notes: Stage half built.')
  await expect(page.getByRole('region', { name: 'History' })).toBeVisible()
  await expect(page.getByRole('main').getByRole('button')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Registrants' })).toHaveCount(0)
})

test('SCRUM-24 AC10: the Lead opens an event from oversight and sees who holds it', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.lead)
  await page.goto('/staff/oversight')

  await page
    .getByRole('region', { name: 'Active events' })
    .getByRole('article', { name: 'Harbourfront Gala Dinner' })
    .getByRole('link', { name: 'Open the event record' })
    .click()

  await expect(page).toHaveURL('/staff/events/EVR-LEAD0003')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Harbourfront Gala Dinner' }),
  ).toBeVisible()
  await expect(page.getByRole('region', { name: 'Coordinator' })).toContainText('Chloe Lim')
})
