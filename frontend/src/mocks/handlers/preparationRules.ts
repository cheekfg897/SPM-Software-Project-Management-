import type { FieldErrors } from '@/lib/api'

/**
 * The preparation rules the venue and equipment modules share (backend/app/common/preparation.py
 * and each module's UpdatePreparationSchema; SCRUM-84, SCRUM-85), in the backend's wording.
 */

const PREPARATION_STATUSES: readonly unknown[] = ['not_started', 'in_progress', 'ready']
const PREPARATION_NOTES_MAX_LENGTH = 1000
/** All an update may send: nothing else of the booking or reservation can change (AC3). */
const PREPARATION_FIELDS: readonly string[] = ['status', 'notes']

export const PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE =
  "Preparation details can't be recorded until the Safety Officer has approved the event's" +
  ' Operational Safety Check.'

/** The notes as the backend saves them: trimmed, or null when they were left out. */
export function savedNotes(body: Record<string, unknown>): string | null {
  return typeof body.notes === 'string' ? body.notes.trim() : null
}

/** Why the status is refused, in marshmallow's words for a required Enum field; null if it isn't. */
function statusError(status: unknown): string | null {
  if (status === undefined) {
    return 'Missing data for required field.'
  }
  if (status === null) {
    return 'Field may not be null.'
  }
  if (!PREPARATION_STATUSES.includes(status)) {
    return 'Status must be not_started, in_progress or ready.'
  }
  return null
}

/** Why the notes are refused, as the shared notes schema words it; null if they aren't. */
function notesError(notes: unknown): string | null {
  // Left out or null, they are cleared.
  if (notes === undefined || notes === null) {
    return null
  }
  if (typeof notes !== 'string') {
    return 'Not a valid string.'
  }
  const trimmed = notes.trim()
  if (trimmed === '') {
    return 'Must not be blank.'
  }
  if (trimmed.length > PREPARATION_NOTES_MAX_LENGTH) {
    return `Notes must be at most ${PREPARATION_NOTES_MAX_LENGTH} characters.`
  }
  return null
}

/** Problems with a preparation update, by field. */
export function preparationErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const name of Object.keys(body)) {
    if (!PREPARATION_FIELDS.includes(name)) {
      errors[name] = ['Unknown field.']
    }
  }
  const status = statusError(body.status)
  if (status !== null) {
    errors.status = [status]
  }
  const notes = notesError(body.notes)
  if (notes !== null) {
    errors.notes = [notes]
  }
  return errors
}
