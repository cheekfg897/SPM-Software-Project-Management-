import { formText } from '@/features/auth/formText'
import { toTimeInputValue } from '@/lib/businessTime'

import type { EventEditChanges, EventRecord } from './api'

/**
 * The coordinator's edit form (SCRUM-33 AC1, AC2; ADR-0025, ADR-0079): what each field shows
 * when it opens, and what it sends. Only the fields that differ from the record are sent, so a
 * date moved on its own lets the backend move the end date by as many days, and an emptied
 * field goes as null. Whether a value is allowed is the backend's to say.
 */

/** Every field the form shows the record's value in, named as the API names it. */
export const SHOWN_FIELDS = [
  'description',
  'programme_notes',
  'accessibility_needs',
  'proposed_date',
  'end_date',
  'start_time',
  'end_time',
  'expected_attendance',
  'venue_requirements',
  'equipment_requirements',
] as const

export type ShownField = (typeof SHOWN_FIELDS)[number]

const TIME_FIELDS: readonly ShownField[] = ['start_time', 'end_time']

/** What `field` shows when the form opens: the saved value, '' for none, a time to the minute. */
export function openingValue(record: EventRecord, field: ShownField): string {
  const saved = record[field]
  if (saved === null) {
    return ''
  }
  const typed = String(saved)
  return TIME_FIELDS.includes(field) ? toTimeInputValue(typed) : typed
}

/**
 * Of `fields`, the ones whose typed value differs from what `record` holds, as the backend wants
 * them: the attendance as a number, and an emptied field as null.
 */
export function differingFields(
  form: FormData,
  record: EventRecord,
  fields: readonly ShownField[],
): EventEditChanges {
  const changes: EventEditChanges = {}
  for (const field of fields) {
    const typed = formText(form, field)
    if (typed === openingValue(record, field)) {
      continue
    }
    if (field === 'expected_attendance') {
      changes.expected_attendance = typed === '' ? null : Number(typed)
    } else {
      changes[field] = typed === '' ? null : typed
    }
  }
  return changes
}

/** The fields the coordinator changed on `record`, as the backend wants them. */
export function changedFields(form: FormData, record: EventRecord): EventEditChanges {
  const changes = differingFields(form, record, SHOWN_FIELDS)
  // The record never shows these notes, so the field opens empty: only what is typed is sent.
  const internalNotes = formText(form, 'internal_planning_notes')
  if (internalNotes !== '') {
    changes.internal_planning_notes = internalNotes
  }
  return changes
}
