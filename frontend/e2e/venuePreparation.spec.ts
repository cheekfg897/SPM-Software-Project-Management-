import { expect, test } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { expectHeaderControlsWithin } from './headerFits'
import { logIn } from './logIn'
import { signInAs } from './signInAs'

/**
 * SCRUM-84: Venue Staff open their booking requests from the header, find an approved booking
 * and record how far its preparation has got (ADR-0080). Against the mock backend.
 */

/** A small phone: narrower than the mobile project's Pixel 7. */
const SMALL_PHONE = { width: 360, height: 740 }

test('SCRUM-84: Venue Staff record an approved booking as ready', async ({ page }) => {
  await page.goto(ROUTES.STAFF_LOGIN)
  await logIn(page, MOCK_ACCOUNTS.venueStaff)
  await expect(page).toHaveURL(ROUTES.STAFF_HOME)

  await page.getByRole('banner').getByRole('link', { name: 'Venue bookings' }).click()
  await expect(page).toHaveURL(ROUTES.BOOKING_DECISIONS)
  const ballroom = page.getByRole('article', { name: 'Grand ballroom' })
  await expect(ballroom).toContainText('Preparation: In progress')

  await ballroom.getByLabel('Preparation status for Grand ballroom').selectOption('ready')
  await ballroom.getByLabel('Preparation notes for Grand ballroom').fill('Stage built, chairs out.')
  await ballroom.getByRole('button', { name: 'Save preparation for Grand ballroom' }).click()

  await expect(ballroom).toContainText('Preparation: Ready')
  await expect(ballroom).toContainText('Preparation notes: Stage built, chairs out.')
})

test('every header control fits on a small phone for Venue Staff', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.venueStaff)
  await page.setViewportSize(SMALL_PHONE)
  await page.goto(ROUTES.BOOKING_DECISIONS)
  await expect(page.getByRole('banner').getByRole('link', { name: 'Venue bookings' })).toBeVisible()

  await expectHeaderControlsWithin(page, SMALL_PHONE.width)
})
