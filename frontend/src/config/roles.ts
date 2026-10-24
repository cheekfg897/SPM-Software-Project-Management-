/** The seven roles, spelt as the backend spells them (app/modules/auth/permissions.py). */
export const ROLE = {
  EVENT_ORGANISER: 'event_organiser',
  ATTENDEE: 'attendee',
  EVENT_COORDINATOR: 'event_coordinator',
  EVENT_COORDINATOR_LEAD: 'event_coordinator_lead',
  VENUE_STAFF: 'venue_staff',
  TECHNICAL_SUPPORT_STAFF: 'technical_support_staff',
  SAFETY_OFFICER: 'safety_officer',
} as const

export type Role = (typeof ROLE)[keyof typeof ROLE]

/** Roles a person can sign up as (SCRUM-65). */
export const EXTERNAL_ROLES: readonly Role[] = [ROLE.EVENT_ORGANISER, ROLE.ATTENDEE]

/** Staff roles. Their accounts are created by `flask create-staff-user` (ADR-0023). */
export const INTERNAL_ROLES: readonly Role[] = [
  ROLE.EVENT_COORDINATOR,
  ROLE.EVENT_COORDINATOR_LEAD,
  ROLE.VENUE_STAFF,
  ROLE.TECHNICAL_SUPPORT_STAFF,
  ROLE.SAFETY_OFFICER,
]

/**
 * Staff who read an event's equipment: Technical Support for any event, a coordinator only for
 * an event assigned to them (the backend decides which events; ADR-0019, ADR-0037).
 */
export const EQUIPMENT_READER_ROLES: readonly Role[] = [
  ROLE.EVENT_COORDINATOR,
  ROLE.TECHNICAL_SUPPORT_STAFF,
]

/**
 * Staff who open any submitted event's read-only record (SCRUM-24 AC9, AC10; ADR-0095). An Event
 * Coordinator opens only their own events, on their own page.
 */
export const STAFF_RECORD_READER_ROLES: readonly Role[] = [
  ROLE.VENUE_STAFF,
  ROLE.TECHNICAL_SUPPORT_STAFF,
  ROLE.SAFETY_OFFICER,
  ROLE.EVENT_COORDINATOR_LEAD,
]

const ALL_ROLES: readonly string[] = Object.values(ROLE)

export function isRole(value: unknown): value is Role {
  return typeof value === 'string' && ALL_ROLES.includes(value)
}
