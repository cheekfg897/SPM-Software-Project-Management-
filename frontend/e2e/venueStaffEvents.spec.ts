import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'

/**
 * SCRUM-24 AC4: Venue Staff log in and find, on Staff home, every event with a venue booking
 * request or a booking (ADR-0085, ADR-0090), each opening its read-only record (AC9, ADR-0095).
 * Against the mock backend.
 */

test('SCRUM-24 AC4: Venue Staff log in and see the events with venue bookings', async ({
  page,
}) => {
  await page.goto('/staff/login')

  await logIn(page, MOCK_ACCOUNTS.venueStaff)

  await expect(page).toHaveURL('/staff')
  const events = page.getByRole('list', { name: 'Events with venue bookings' })
  // In mock mode the app mounts once the mock worker starts: wait for a row before counting them.
  const workshop = events.getByRole('listitem').filter({ hasText: 'Design Workshop' })
  await expect(workshop).toContainText('Fri, 20 Nov · 9:00 am – 5:00 pm')
  await expect(workshop).toContainText('EVR-BOOK0105')
  await expect(workshop).toContainText('Approved')
  // Every booking mock event with an active venue arrangement, EVR-BOOK0104 to EVR-BOOK0112.
  await expect(events.getByRole('listitem')).toHaveCount(9)
  await expect(events.getByRole('link')).toHaveCount(9)
})
