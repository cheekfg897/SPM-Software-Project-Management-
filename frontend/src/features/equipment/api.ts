import { apiRequest } from '@/lib/api'

/** The equipment API: backend/app/modules/equipment/routes.py. Events are named by EVR- reference. */
const EQUIPMENT_PATHS = {
  AVAILABILITY: (reference: string) => `/api/equipment/events/${reference}/availability`,
  RESERVATIONS: (reference: string) => `/api/equipment/events/${reference}/reservations`,
} as const

/** What is free of one equipment type for the event's own period, against what it asks for. */
export interface EquipmentAvailability {
  equipment_type_id: number
  equipment_type_name: string
  available: number
  requested: number
  shortfall: number
}

/** Equipment held for an event. `reserved_by` is the reserver's name, null once their account is gone. */
export interface EquipmentReservation {
  id: number
  equipment_type_id: number
  equipment_type_name: string
  quantity: number
  /** ISO date-time with an offset, in business time. */
  starts_at: string
  ends_at: string
  reserved_by: string | null
  created_at: string
}

export interface ReserveEquipmentBody {
  equipment_type_id: number
  quantity: number
}

export const equipmentKeys = {
  all: ['equipment'] as const,
  /** Everything about one event's equipment: reserving changes both of the lists below. */
  event: (reference: string) => [...equipmentKeys.all, reference] as const,
  availability: (reference: string) => [...equipmentKeys.event(reference), 'availability'] as const,
  reservations: (reference: string) => [...equipmentKeys.event(reference), 'reservations'] as const,
}

export function fetchEventAvailability(reference: string): Promise<EquipmentAvailability[]> {
  return apiRequest<EquipmentAvailability[]>(EQUIPMENT_PATHS.AVAILABILITY(reference))
}

export function fetchEventReservations(reference: string): Promise<EquipmentReservation[]> {
  return apiRequest<EquipmentReservation[]>(EQUIPMENT_PATHS.RESERVATIONS(reference))
}

/** Reserve units of one equipment type for the event. Technical Support Staff only. */
export function reserveEquipment(
  reference: string,
  body: ReserveEquipmentBody,
): Promise<EquipmentReservation> {
  return apiRequest<EquipmentReservation>(EQUIPMENT_PATHS.RESERVATIONS(reference), {
    method: 'POST',
    body,
  })
}
