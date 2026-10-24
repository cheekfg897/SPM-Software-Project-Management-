import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'

/**
 * SCRUM-38 and SCRUM-24 AC5: Technical Support find the equipment awaiting them and the events
 * with equipment on Staff home, and open an event's Equipment page from either: straight from the
 * queue, or through the event's read-only record from the events with equipment (ADR-0061,
 * ADR-0095).
 * Against the mock backend.
 */

test('SCRUM-38: Technical Support log in, find the soonest equipment and open its event', async ({
  page,
}) => {
  await page.goto('/staff/login')

  await logIn(page, MOCK_ACCOUNTS.technicalSupport)

  await expect(page).toHaveURL('/staff')
  const queue = page.getByRole('list', { name: 'Equipment awaiting action' })
  // In mock mode the app mounts once the mock worker starts: wait for a row before reading them.
  await expect(queue.getByRole('heading', { name: 'Sunrise Wellness Walk' })).toBeVisible()
  await expect(queue.getByRole('listitem')).toHaveCount(7)
  const showcase = queue.getByRole('link', { name: /Evening Product Showcase/ })
  await expect(showcase).toContainText('Projector × 2, Microphone × 4')
  await expect(showcase).toContainText('7 days left')

  await showcase.click()

  await expect(page).toHaveURL('/events/EVR-MOCK0001/equipment')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Equipment for EVR-MOCK0001' }),
  ).toBeVisible()
  await expect(page.getByRole('table', { name: 'Equipment availability' })).toBeVisible()
})

test('SCRUM-24 AC5: Technical Support open a cancelled event from the events with equipment', async ({
  page,
}) => {
  await page.goto('/staff/login')
  await logIn(page, MOCK_ACCOUNTS.technicalSupport)

  await expect(page).toHaveURL('/staff')
  const events = page.getByRole('list', { name: 'Events with equipment' })
  const cancelled = events.getByRole('link', { name: /Product Launch Evening/ })
  await expect(cancelled).toContainText('Cancelled')

  await cancelled.click()
  await expect(page).toHaveURL('/staff/events/EVR-MOCK0002')
  await page.getByRole('main').getByRole('link', { name: 'Equipment' }).click()

  await expect(page).toHaveURL('/events/EVR-MOCK0002/equipment')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Equipment for EVR-MOCK0002' }),
  ).toBeVisible()
})
