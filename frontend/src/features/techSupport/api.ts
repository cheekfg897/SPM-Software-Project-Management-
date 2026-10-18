import type { EventRequest } from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'

/** Technical Support's queue (backend/app/modules/events). */
const TECH_SUPPORT_PATHS = {
  AWAITING_EQUIPMENT: '/api/events/requests/awaiting-equipment',
} as const

/** An event as the equipment lists show it: its name, dates and times (ADR-0019, ADR-0022). */
export type EquipmentEvent = Pick<
  EventRequest,
  'reference' | 'name' | 'proposed_date' | 'end_date' | 'start_time' | 'end_time'
>

/** Where a line stands: `requested` until Technical Support record an outcome (SCRUM-48). */
export type EquipmentLineStatus = 'requested' | 'fulfilled' | 'partially_fulfilled' | 'unavailable'

/** One equipment line: a type, by id only, and how many of it (SCRUM-37 AC4). */
export interface EquipmentLine {
  id: number
  equipment_type_id: number
  quantity: number
  notes: string | null
  status: EquipmentLineStatus
}

/**
 * One event's equipment still awaiting Technical Support: only its lines still `requested`, and
 * the whole days until the event, 0 on the day (SCRUM-38 AC2, ADR-0022).
 */
export interface EquipmentAwaitingAction {
  event: EquipmentEvent
  equipment_lines: EquipmentLine[]
  days_remaining: number
}

/** The queue, soonest event first. Unlike the event lists, an empty one has no message. */
export interface EquipmentAwaitingList {
  equipment_requests: EquipmentAwaitingAction[]
}

/** An equipment type: the catalogue's (SCRUM-27), which the queue's lines are named from. */
export type { EquipmentType } from '@/features/equipmentCatalogue/api'

/**
 * The queue is the same for every Technical Support member and nobody else asks, so the viewer
 * isn't part of its key; signing out clears the cache (ADR-0061).
 */
export const techSupportKeys = {
  all: ['techSupport'] as const,
  awaitingEquipment: () => [...techSupportKeys.all, 'awaitingEquipment'] as const,
}

/** Every upcoming event's equipment still awaiting Technical Support, soonest first (SCRUM-38). */
export function fetchEquipmentAwaitingAction(): Promise<EquipmentAwaitingList> {
  return apiRequest<EquipmentAwaitingList>(TECH_SUPPORT_PATHS.AWAITING_EQUIPMENT)
}
