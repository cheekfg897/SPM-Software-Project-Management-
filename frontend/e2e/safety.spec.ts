import { expect, test } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'
import { signInAs } from './signInAs'

/**
 * SCRUM-97 and SCRUM-98: the Safety Officer logs in, lands on the events awaiting the safety
 * check, records an outcome for one, and it leaves the list.
 */

const CHECKLIST_LABELS = [
  'Expected attendance versus venue capacity',
  'Venue layout',
  'Emergency access',
  'Accessibility requirements',
  'Equipment placement',
  'Crowd movement',
  'Known venue restrictions',
]
/** Two of the mock's events (src/mocks/handlers/safetyFixtures.ts). */
const GALA = 'Harbour Lights Gala'
const FAIR = 'Community Health Fair'
const SMALL_PHONE = { width: 360, height: 740 }

test('the Safety Officer records a safety check and the event leaves their list', async ({
  page,
}) => {
  await page.goto(ROUTES.STAFF_LOGIN)
  await logIn(page, MOCK_ACCOUNTS.safetyOfficer)

  await expect(page).toHaveURL(ROUTES.SAFETY_REVIEW)
  const gala = page.getByRole('article', { name: GALA })
  await expect(gala.getByText('Marina Ballroom')).toBeVisible()

  await gala.getByRole('button', { name: 'Record safety check' }).click()
  for (const label of CHECKLIST_LABELS) {
    await gala.getByLabel(label, { exact: true }).fill(`Checked: ${label}.`)
  }
  await gala.getByLabel('Reason', { exact: true }).fill('The second exit is blocked by staging.')
  await gala.getByRole('button', { name: `Request changes ${GALA}` }).click()

  const notice = page.getByRole('status')
  await expect(notice).toContainText(`Safety check recorded for ${GALA}: Request changes.`)
  await expect(notice).toContainText('Approved')
  await expect(gala).toHaveCount(0)
  await expect(page.getByRole('article', { name: FAIR })).toBeVisible()
})

test('every header control fits on a small phone for the Safety Officer', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.safetyOfficer)
  await page.setViewportSize(SMALL_PHONE)
  await page.goto(ROUTES.SAFETY_REVIEW)
  const header = page.getByRole('banner')
  await expect(header.getByRole('link', { name: 'Safety review' })).toBeVisible()

  const controls = await header.locator('a, button').all()
  for (const control of controls) {
    const box = await control.boundingBox()
    expect(box, await control.innerText()).not.toBeNull()
    expect(box!.x + box!.width, await control.innerText()).toBeLessThanOrEqual(SMALL_PHONE.width)
  }
})
