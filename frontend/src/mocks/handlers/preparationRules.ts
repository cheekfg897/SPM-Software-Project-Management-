import type { FieldErrors } from '@/lib/api'

/**
 * The preparation rules the venue and equipment modules share (backend/app/common/preparation.py
 * and each module's UpdatePreparationSchema; SCRUM-84, SCRUM-85), in the backend's wording.
 */

const PREPARATION_STATUSES: readonly unknown[] = ['not_started', 'in_progress', 'ready']
const PREPARATION_NOTES_MAX_LENGTH = 1000

export const PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE =
  "Preparation details can't be recorded until the Safety Officer has approved the event's" +
  ' Operational Safety Check.'

/** The notes as the backend saves them: trimmed, or null when they were left out. */
export function savedNotes(body: Record<string, unknown>): string | null {
  return typeof body.notes === 'string' ? body.notes.trim() : null
}

/** Problems with a preparation update, by field. */
export function preparationErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  if (body.status === undefined) {
    errors.status = ['Missing data for required field.']
  } else if (!PREPARATION_STATUSES.includes(body.status)) {
    errors.status = ['Status must be not_started, in_progress or ready.']
  }
  const notes = savedNotes(body)
  if (notes === '') {
    errors.notes = ['Must not be blank.']
  } else if (notes !== null && notes.length > PREPARATION_NOTES_MAX_LENGTH) {
    errors.notes = [`Notes must be at most ${PREPARATION_NOTES_MAX_LENGTH} characters.`]
  }
  return errors
}
