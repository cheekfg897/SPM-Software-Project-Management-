import { MOCK_ACCOUNTS } from '../fixtures/accounts'

/**
 * Data for the equipment mock (backend/app/modules/equipment). Every mock event shares one
 * period, so a reservation for one lowers what is free for all of them.
 */

export const MOCK_OPEN_EVENT_REFERENCE = 'EVR-MOCK0001'
export const MOCK_CLOSED_EVENT_REFERENCE = 'EVR-MOCK0002'

export const MOCK_EVENT_PERIOD = {
  starts_at: '2026-10-12T19:30:00+08:00',
  ends_at: '2026-10-12T22:00:00+08:00',
}

export interface MockEquipmentType {
  id: number
  name: string
  /** Units free for the period before anything is reserved through the mock. */
  free: number
  /** Units the mock events ask for. */
  requested: number
}

/** Ten projectors held, four reserved by other events, leaves six free against eight asked for. */
export const MOCK_EQUIPMENT_TYPES: readonly MockEquipmentType[] = [
  { id: 1, name: 'Projector', free: 6, requested: 8 },
  { id: 2, name: 'Microphone', free: 12, requested: 4 },
]

interface MockEvent {
  /** A closed event is completed, cancelled or rejected: nothing can be reserved for it. */
  accepts_reservations: boolean
  /** The assigned coordinator's account id; only they, of the coordinators, read its equipment. */
  coordinator_id: number | null
}

/** Events that exist. The open one is the mock coordinator's; nobody is assigned the closed one. */
export const MOCK_EVENT_REFERENCES: Record<string, MockEvent> = {
  [MOCK_OPEN_EVENT_REFERENCE]: {
    accepts_reservations: true,
    coordinator_id: MOCK_ACCOUNTS.coordinator.id,
  },
  [MOCK_CLOSED_EVENT_REFERENCE]: { accepts_reservations: false, coordinator_id: null },
}
