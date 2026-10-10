import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

import { resetMockNotifications } from './notifications'

/** The notifications mock stands in for SCRUM-28's backend (routes.py in the notifications module). */

interface Row {
  id: number
  kind: string
  message: string
  event_reference: string
  event_name: string
  link: string
  created_at: string
  read_at: string | null
  detail: string | null
}

const PATH = '/api/notifications'

function listAs(account: (typeof MOCK_ACCOUNTS)[keyof typeof MOCK_ACCOUNTS]) {
  sendRequestsAs(mockTokenFor(account))
  return apiRequest<{ notifications: Row[] }>(PATH).then((body) => body.notifications)
}

function markRead(id: number) {
  return apiRequest<Row>(`${PATH}/${id}/read`, { method: 'POST' })
}

describe('SCRUM-28 notifications mock', () => {
  it('seeds each account with unread and read notifications, one with no detail', async () => {
    const rows = await listAs(MOCK_ACCOUNTS.attendee)

    expect(rows.filter((row) => row.read_at === null).length).toBeGreaterThanOrEqual(2)
    expect(rows.filter((row) => row.read_at !== null).length).toBeGreaterThanOrEqual(1)
    expect(rows.some((row) => row.detail === null)).toBe(true)
    expect(Object.keys(rows[0] ?? {}).sort()).toEqual(
      [
        'id',
        'kind',
        'message',
        'event_reference',
        'event_name',
        'link',
        'created_at',
        'read_at',
        'detail',
      ].sort(),
    )
    expect(rows[0]?.link).toBe(`/events/${rows[0]?.event_reference}`)
  })

  it('shows each account only its own notifications', async () => {
    const attendeeIds = (await listAs(MOCK_ACCOUNTS.attendee)).map((row) => row.id)
    const organiserIds = (await listAs(MOCK_ACCOUNTS.organiser)).map((row) => row.id)

    expect(organiserIds.length).toBeGreaterThanOrEqual(3)
    expect(organiserIds.filter((id) => attendeeIds.includes(id))).toEqual([])
  })

  it('answers 404 for another account notification, as for a missing one', async () => {
    const [organiserRow] = await listAs(MOCK_ACCOUNTS.organiser)
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.attendee))

    await expect(markRead(organiserRow?.id ?? 0)).rejects.toMatchObject({ status: 404 })
    await expect(markRead(99999)).rejects.toMatchObject({ status: 404 })
  })

  it('answers 401 without a token', async () => {
    sendRequestsAs(null)

    await expect(apiRequest(PATH)).rejects.toMatchObject({ status: 401 })
    await expect(apiRequest(`${PATH}/unread-count`)).rejects.toMatchObject({ status: 401 })
  })

  it('keeps the first read time when a notification is marked read twice', async () => {
    const rows = await listAs(MOCK_ACCOUNTS.attendee)
    const unread = rows.find((row) => row.read_at === null)

    const first = await markRead(unread?.id ?? 0)
    const second = await markRead(unread?.id ?? 0)

    expect(second.read_at).toBe(first.read_at)
  })

  it('puts the data back as seeded on reset', async () => {
    const rows = await listAs(MOCK_ACCOUNTS.attendee)
    await markRead(rows.find((row) => row.read_at === null)?.id ?? 0)

    resetMockNotifications()

    expect(await listAs(MOCK_ACCOUNTS.attendee)).toEqual(rows)
  })
})
