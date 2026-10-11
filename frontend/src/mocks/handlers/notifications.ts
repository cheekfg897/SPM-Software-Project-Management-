import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import type { Notification } from '@/features/notifications/api'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'
import { errorResponse, INVALID_TOKEN_MESSAGE } from '../responses'

import { accountForRequest } from './auth'

/**
 * The notification endpoints as backend/app/modules/notifications/routes.py has them. Each
 * account sees only its own, and the messages and links are the backend's, as sent.
 */

const NOTIFICATIONS_PATH = '/api/notifications'

const KINDS = {
  coordinatorAssigned: {
    kind: 'coordinator_assigned',
    message: 'You have been assigned to coordinate this event.',
  },
  equipmentRequested: {
    kind: 'equipment_requested',
    message: 'Equipment was requested for an event.',
  },
  requestSubmitted: {
    kind: 'event_request_submitted',
    message: 'A new event request was submitted.',
  },
} as const

/** A notification and whose it is. The recipient is not part of what the backend sends. */
interface StoredNotification {
  recipientId: number
  notification: Notification
}

interface SeedOptions {
  id: number
  recipientId: number
  kind: keyof typeof KINDS
  eventName: string
  createdAt: string
  readAt?: string
  detail?: string
}

/** A notification as the backend would send it; the event reference follows from the id. */
function seed(options: SeedOptions): StoredNotification {
  const reference = `EVR-MOCK${String(options.id).padStart(4, '0')}`
  const notification: Notification = {
    id: options.id,
    kind: KINDS[options.kind].kind,
    message: KINDS[options.kind].message,
    event_reference: reference,
    event_name: options.eventName,
    link: `/events/${reference}`,
    created_at: options.createdAt,
    read_at: options.readAt ?? null,
    detail: options.detail ?? null,
  }
  return { recipientId: options.recipientId, notification }
}

/**
 * Three each: two unread and one read, the read one without a detail. They are stored
 * oldest first, as a table fills, so the list handler has to sort to put the newest first.
 */
function seedNotifications(): StoredNotification[] {
  const attendee = MOCK_ACCOUNTS.attendee.id
  const organiser = MOCK_ACCOUNTS.organiser.id
  const coordinator = MOCK_ACCOUNTS.coordinator.id
  const newestFirst = [
    seed({
      id: 1,
      recipientId: attendee,
      kind: 'requestSubmitted',
      eventName: 'Jazz by the Bay',
      createdAt: '2026-10-05T09:00:00+08:00',
      detail: 'Doors open at 7pm.',
    }),
    seed({
      id: 2,
      recipientId: attendee,
      kind: 'equipmentRequested',
      eventName: 'Pitch Night',
      createdAt: '2026-10-04T15:30:00+08:00',
      detail: 'Two microphones.',
    }),
    seed({
      id: 3,
      recipientId: attendee,
      kind: 'coordinatorAssigned',
      eventName: 'Board Game Social',
      createdAt: '2026-10-03T11:00:00+08:00',
      readAt: '2026-10-03T12:00:00+08:00',
    }),
    seed({
      id: 4,
      recipientId: organiser,
      kind: 'coordinatorAssigned',
      eventName: 'Founders Breakfast',
      createdAt: '2026-10-05T10:15:00+08:00',
      detail: 'Assigned to Chloe Lim.',
    }),
    seed({
      id: 5,
      recipientId: organiser,
      kind: 'requestSubmitted',
      eventName: 'Robotics Showcase',
      createdAt: '2026-10-04T08:45:00+08:00',
      detail: 'Awaiting review.',
    }),
    seed({
      id: 6,
      recipientId: organiser,
      kind: 'equipmentRequested',
      eventName: 'Film Screening',
      createdAt: '2026-10-02T17:00:00+08:00',
      readAt: '2026-10-02T18:30:00+08:00',
    }),
    seed({
      id: 7,
      recipientId: coordinator,
      kind: 'coordinatorAssigned',
      eventName: 'Career Fair Kickoff',
      createdAt: '2026-10-05T11:30:00+08:00',
      detail: 'Hall B, 200 guests.',
    }),
    seed({
      id: 8,
      recipientId: coordinator,
      kind: 'equipmentRequested',
      eventName: 'Hack Night',
      createdAt: '2026-10-04T13:20:00+08:00',
      detail: 'Projector and 4 extension leads.',
    }),
    seed({
      id: 9,
      recipientId: coordinator,
      kind: 'requestSubmitted',
      eventName: 'Charity Run Briefing',
      createdAt: '2026-10-01T09:10:00+08:00',
      readAt: '2026-10-01T10:00:00+08:00',
    }),
  ]
  return newestFirst.reverse()
}

let stored = seedNotifications()
let readClock = 0

/** Put the notifications back as seeded, so no test sees another's reads. Runs after every test. */
export function resetMockNotifications(): void {
  stored = seedNotifications()
  readClock = 0
}

function notificationsOf(userId: number): Notification[] {
  return stored.filter((entry) => entry.recipientId === userId).map((entry) => entry.notification)
}

export const notificationHandlers: RequestHandler[] = [
  http.get(NOTIFICATIONS_PATH, ({ request }) => {
    const user = accountForRequest(request)
    if (user === undefined) {
      return errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE)
    }

    const newestFirst = notificationsOf(user.id).sort((first, second) =>
      second.created_at.localeCompare(first.created_at),
    )
    return HttpResponse.json({ notifications: newestFirst })
  }),

  http.get(`${NOTIFICATIONS_PATH}/unread-count`, ({ request }) => {
    const user = accountForRequest(request)
    if (user === undefined) {
      return errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE)
    }

    const unread = notificationsOf(user.id).filter((notification) => notification.read_at === null)
    return HttpResponse.json({ unread_count: unread.length })
  }),

  http.post(`${NOTIFICATIONS_PATH}/:notificationId/read`, ({ request, params }) => {
    const user = accountForRequest(request)
    if (user === undefined) {
      return errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE)
    }

    // Someone else's notification is a 404, the same as a missing one.
    const notification = notificationsOf(user.id).find(
      (candidate) => String(candidate.id) === params.notificationId,
    )
    if (notification === undefined) {
      return errorResponse(404, 'not_found', 'Notification not found.')
    }

    if (notification.read_at === null) {
      readClock += 1
      notification.read_at = `2026-10-05T12:${String(readClock).padStart(2, '0')}:00+08:00`
    }
    return HttpResponse.json(notification)
  }),
]
