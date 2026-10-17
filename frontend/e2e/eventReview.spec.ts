import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'

/**
 * SCRUM-31, SCRUM-32: a coordinator starts reviewing a request and asks the organiser a
 * question; the organiser answers it; the coordinator then approves the request (ADR-0049).
 * Against the mock backend, which keeps its data only until the page reloads, so the journey
 * switches users through the app's own log-out and log-in, never by reloading.
 */

const COORDINATOR = MOCK_ACCOUNTS.reviewingCoordinator
const ORGANISER = MOCK_ACCOUNTS.otherOrganiser
const EVENT_NAME = 'Community Hackathon'
const QUESTION = 'Is the hall step-free for wheelchair users?'
const ANSWER = 'Yes, the side entrance has a ramp.'

/** Leave through the header, and wait for the public home page. */
async function logOut(page: Page) {
  await page.getByRole('banner').getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL('/')
}

/** Log in on the staff page, reached from the footer, and open the event from Staff home. */
async function openAsCoordinator(page: Page) {
  await page.getByRole('link', { name: 'Staff log in' }).click()
  await expect(page).toHaveURL('/staff/login')
  await logIn(page, COORDINATOR)
  await expect(page).toHaveURL('/staff')
  const assigned = page.getByRole('list', { name: 'Your assigned events' })
  await assigned.getByRole('link', { name: new RegExp(EVENT_NAME) }).click()
  await expect(page).toHaveURL('/events/EVR-RV4K8N2P')
}

test('SCRUM-31, SCRUM-32: a coordinator reviews a request, asks a question, and approves it once the organiser answers', async ({
  page,
}) => {
  await page.goto('/')
  await openAsCoordinator(page)

  await page.getByRole('button', { name: 'Start review' }).click()
  await expect(page.getByText('Under review', { exact: true })).toBeVisible()
  await page.getByLabel('Question').fill(QUESTION)
  await page.getByRole('button', { name: 'Ask for clarification' }).click()

  const clarifications = page.getByRole('region', { name: 'Clarifications' })
  await expect(clarifications).toContainText(QUESTION)
  await expect(clarifications).toContainText('Waiting for an answer.')
  await expect(page.getByRole('button', { name: 'Approve' })).toHaveCount(0)

  await logOut(page)
  await page.getByRole('banner').getByRole('link', { name: 'Log in' }).click()
  await logIn(page, ORGANISER)
  await expect(page).toHaveURL('/organiser')
  const requests = page.getByRole('list', { name: 'Your event requests' })
  await requests.getByRole('link', { name: new RegExp(EVENT_NAME) }).click()
  await expect(page).toHaveURL('/organiser/requests/EVR-RV4K8N2P')
  await expect(page.getByText('Awaiting clarification', { exact: true })).toBeVisible()

  await page.getByLabel('Your answer').fill(ANSWER)
  await page.getByRole('button', { name: 'Send answer' }).click()

  await expect(clarifications).toContainText(ANSWER)
  await expect(clarifications).toContainText('Answered by Sara Lee')
  await expect(page.getByText('Under review', { exact: true })).toBeVisible()

  await logOut(page)
  await openAsCoordinator(page)
  await page.getByRole('button', { name: 'Approve' }).click()

  const decision = page.getByRole('region', { name: 'Decision' })
  await expect(decision).toContainText('Approved')
  await expect(decision).toContainText('Decided by Priya Nair')
})
