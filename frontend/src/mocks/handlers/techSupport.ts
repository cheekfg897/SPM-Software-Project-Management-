import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import type { EventListRow } from '@/features/eventRequests/api'
import type { EquipmentAwaitingAction, EquipmentEvent } from '@/features/techSupport/api'

import { notAllowed, notAuthenticated } from '../responses'

import { accountForRequest } from './auth'
import { MOCK_TODAY } from './catalogueFixtures'
import { MOCK_EQUIPMENT_EVENTS } from './techSupportFixtures'
import type { MockEquipmentEvent } from './techSupportFixtures'

/**
 * Technical Support's two lists, as backend/app/modules/events/routes.py answers them: the
 * equipment awaiting action (SCRUM-38, ADR-0022) and the events with equipment (SCRUM-24 AC5,
 * ADR-0026), both for Technical Support only. The equipment types their lines are named from are
 * answered by the catalogue mock, equipmentCatalogue.ts (ADR-0061).
 */

const AWAITING_EQUIPMENT_PATH = '/api/events/requests/awaiting-equipment'
const WITH_EQUIPMENT_PATH = '/api/events/requests/with-equipment'
const NO_EQUIPMENT_REQUESTS_MESSAGE = 'No events have an equipment request yet.'
const DAY_MS = 24 * 60 * 60_000

/** Events that won't run, so their equipment isn't awaited (EQUIPMENT_NOT_NEEDED_STATUSES). */
const EQUIPMENT_NOT_NEEDED: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.COMPLETED,
  EVENT_REQUEST_STATUS.CANCELLED,
  EVENT_REQUEST_STATUS.REJECTED,
]

/** The 401 or 403 the backend's decorators send, or null when the caller holds one of `roles`. */
function refusalFor(request: Request, roles: readonly Role[]) {
  const account = accountForRequest(request)
  if (account === undefined) {
    return notAuthenticated()
  }
  if (!roles.includes(account.role)) {
    return notAllowed()
  }
  return null
}

/** Whole days from the mock's today to `date`: 0 on the day, 1 the day before (ADR-0022). */
function daysFromToday(date: string): number {
  return (Date.parse(`${date}T00:00:00Z`) - Date.parse(`${MOCK_TODAY}T00:00:00Z`)) / DAY_MS
}

/** Event date, then start time, then as submitted: the queue's order (ADR-0022's point 9). */
function soonestFirst(a: MockEquipmentEvent, b: MockEquipmentEvent): number {
  const byDate = a.event.proposed_date.localeCompare(b.event.proposed_date)
  if (byDate !== 0) {
    return byDate
  }
  const byStart = a.event.start_time.localeCompare(b.event.start_time)
  if (byStart !== 0) {
    return byStart
  }
  return a.id - b.id
}

function newestFirst(a: MockEquipmentEvent, b: MockEquipmentEvent): number {
  return b.createdAt.localeCompare(a.createdAt)
}

/** The event as the equipment lists show it: everything but its status (ADR-0022's point 12). */
function equipmentEventOf(event: EventListRow): EquipmentEvent {
  return {
    reference: event.reference,
    name: event.name,
    proposed_date: event.proposed_date,
    end_date: event.end_date,
    start_time: event.start_time,
    end_time: event.end_time,
  }
}

/** The event's place in the queue, or null when nothing of it is awaited (SCRUM-38 AC1, AC4). */
export function awaitingRow(stored: MockEquipmentEvent): EquipmentAwaitingAction | null {
  const { event } = stored
  if (event.proposed_date < MOCK_TODAY || EQUIPMENT_NOT_NEEDED.includes(event.status)) {
    return null
  }
  const stillRequested = stored.lines.filter((line) => line.status === 'requested')
  if (stillRequested.length === 0) {
    return null
  }
  return {
    event: equipmentEventOf(event),
    equipment_lines: stillRequested,
    days_remaining: daysFromToday(event.proposed_date),
  }
}

/** The body as the backend builds it: its message only when there are no events (AC11). */
export function withEquipmentBody(rows: EventListRow[]) {
  if (rows.length === 0) {
    return { event_requests: rows, message: NO_EQUIPMENT_REQUESTS_MESSAGE }
  }
  return { event_requests: rows }
}

export const techSupportHandlers: RequestHandler[] = [
  http.get(AWAITING_EQUIPMENT_PATH, ({ request }) => {
    const refusal = refusalFor(request, [ROLE.TECHNICAL_SUPPORT_STAFF])
    if (refusal !== null) {
      return refusal
    }

    const queue: EquipmentAwaitingAction[] = []
    for (const stored of [...MOCK_EQUIPMENT_EVENTS].sort(soonestFirst)) {
      const row = awaitingRow(stored)
      if (row !== null) {
        queue.push(row)
      }
    }
    return HttpResponse.json({ equipment_requests: queue })
  }),

  http.get(WITH_EQUIPMENT_PATH, ({ request }) => {
    const refusal = refusalFor(request, [ROLE.TECHNICAL_SUPPORT_STAFF])
    if (refusal !== null) {
      return refusal
    }

    const withLines = MOCK_EQUIPMENT_EVENTS.filter((stored) => stored.lines.length > 0)
    const rows = [...withLines].sort(newestFirst).map((stored) => stored.event)
    return HttpResponse.json(withEquipmentBody(rows))
  }),
]
