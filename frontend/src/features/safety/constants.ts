/**
 * The Safety Officer's three outcomes, as the backend spells them (SafetyOutcome in
 * backend/app/modules/events/models.py, SCRUM-98 AC1).
 */
export const SAFETY_OUTCOME = {
  APPROVED: 'approved',
  REJECTED: 'rejected',
  CHANGES_REQUESTED: 'changes_requested',
} as const

export type SafetyOutcome = (typeof SAFETY_OUTCOME)[keyof typeof SAFETY_OUTCOME]

/** What each outcome's button says: SCRUM-98 AC1's own words. */
export const OUTCOME_ACTION_LABELS: Record<SafetyOutcome, string> = {
  approved: 'Approve',
  rejected: 'Reject',
  changes_requested: 'Request changes',
}

/** The checklist's seven items, as the backend names them (SafetyChecklistSchema). */
export type ChecklistItem =
  | 'attendance_vs_capacity'
  | 'venue_layout'
  | 'emergency_access'
  | 'accessibility'
  | 'equipment_placement'
  | 'crowd_movement'
  | 'venue_restrictions'

/**
 * Hint for the items ConnectSphere holds no data for: the Safety Officer assesses them from
 * their own knowledge (SCRUM-98 AC3, SCRUM-97 scope note).
 */
const NOT_HELD_HINT = 'ConnectSphere holds no data on this. Record your own assessment.'

interface ChecklistEntry {
  item: ChecklistItem
  /** SCRUM-98 AC2's wording for the item. */
  label: string
  hint?: string
}

/** The checklist in SCRUM-98 AC2's order, each item worded as the AC words it. */
export const CHECKLIST: readonly ChecklistEntry[] = [
  { item: 'attendance_vs_capacity', label: 'Expected attendance versus venue capacity' },
  { item: 'venue_layout', label: 'Venue layout' },
  { item: 'emergency_access', label: 'Emergency access', hint: NOT_HELD_HINT },
  { item: 'accessibility', label: 'Accessibility requirements' },
  { item: 'equipment_placement', label: 'Equipment placement', hint: NOT_HELD_HINT },
  { item: 'crowd_movement', label: 'Crowd movement', hint: NOT_HELD_HINT },
  { item: 'venue_restrictions', label: 'Known venue restrictions', hint: NOT_HELD_HINT },
]
