import { expect, test } from '@playwright/test'

import { eventEquipmentPath } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'
import { MOCK_MOVED_EVENT_REFERENCE } from '../src/mocks/handlers/equipmentFixtures'

import { logIn } from './logIn'

/**
 * SCRUM-60: Technical Support find an event whose date changed in their queue, see what its
 * reservations hold against what is free for its period now, and confirm the projectors for it
 * (ADR-0114). Against the mock backend, which starts with that event's reservations marked.
 */

test('SCRUM-60: Technical Support confirm a reservation for the event period now', async ({
  page,
}) => {
  await page.goto('/staff/login')
  await logIn(page, MOCK_ACCOUNTS.technicalSupport)
  await expect(page).toHaveURL('/staff')
  const queue = page.getByRole('list', { name: 'Equipment awaiting action' })
  const offsite = queue.getByRole('link', { name: /Leadership Offsite/ })
  await expect(offsite).toContainText('Projector × 3 (reservation to reassess)')

  await offsite.click()

  await expect(page).toHaveURL(eventEquipmentPath(MOCK_MOVED_EVENT_REFERENCE))
  const toReassess = page.getByRole('list', { name: 'Reservations to reassess' })
  await expect(toReassess.getByRole('listitem')).toHaveCount(2)
  await expect(toReassess).toContainText('Held for 9 Oct, 7:30 pm – 10:00 pm')
  await page.getByRole('button', { name: "Confirm Projector for the event's period now" }).click()
  await expect(toReassess.getByRole('listitem')).toHaveCount(1)
  await expect(toReassess).not.toContainText('Projector')
})
