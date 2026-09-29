/** The five roles, spelt as the backend spells them (app/modules/auth/permissions.py). */
export const ROLE = {
  EVENT_ORGANISER: 'event_organiser',
  ATTENDEE: 'attendee',
  EVENT_COORDINATOR: 'event_coordinator',
  VENUE_STAFF: 'venue_staff',
  TECHNICAL_SUPPORT_STAFF: 'technical_support_staff',
} as const

export type Role = (typeof ROLE)[keyof typeof ROLE]

/** Roles a person can sign up as (SCRUM-65). */
export const EXTERNAL_ROLES: readonly Role[] = [ROLE.EVENT_ORGANISER, ROLE.ATTENDEE]

/** Staff roles. Their accounts are created by `flask create-staff-user` (ADR-0023). */
export const INTERNAL_ROLES: readonly Role[] = [
  ROLE.EVENT_COORDINATOR,
  ROLE.VENUE_STAFF,
  ROLE.TECHNICAL_SUPPORT_STAFF,
]

const ALL_ROLES: readonly string[] = Object.values(ROLE)

export function isRole(value: unknown): value is Role {
  return typeof value === 'string' && ALL_ROLES.includes(value)
}
