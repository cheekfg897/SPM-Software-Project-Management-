import { formText } from '@/features/auth/formText'

import type { EventRequestDetails } from './api'

/** The request form's text fields, named as the API names them. */
const TEXT_FIELDS = [
  'purpose',
  'description',
  'proposed_date',
  'end_date',
  'start_time',
  'end_time',
  'venue_requirements',
  'accessibility_needs',
  'equipment_requirements',
] as const

/**
 * What the organiser filled in, as the backend wants it. A field left empty is left out, so the
 * backend can say which ones a submission needs ("Missing data for required field."), as the
 * booking form does. The attendance goes as a number; every check is the backend's.
 */
export function detailsFromForm(
  form: FormData,
  registrationRequired: boolean,
): EventRequestDetails {
  const details: EventRequestDetails = {
    name: formText(form, 'name'),
    registration_required: registrationRequired,
  }
  for (const field of TEXT_FIELDS) {
    const value = formText(form, field)
    if (value !== '') {
      details[field] = value
    }
  }
  const attendance = formText(form, 'expected_attendance')
  if (attendance !== '') {
    details.expected_attendance = Number(attendance)
  }
  return details
}

/**
 * What the organiser changed on a draft, as the backend wants it (SCRUM-20 AC3). Every field is
 * sent, and an emptied one as null, so the draft forgets what it held (ADR-0024).
 */
export function changesFromForm(
  form: FormData,
  registrationRequired: boolean,
): EventRequestDetails {
  const changes: EventRequestDetails = {
    name: formText(form, 'name'),
    registration_required: registrationRequired,
  }
  for (const field of TEXT_FIELDS) {
    const value = formText(form, field)
    changes[field] = value === '' ? null : value
  }
  const attendance = formText(form, 'expected_attendance')
  changes.expected_attendance = attendance === '' ? null : Number(attendance)
  return changes
}
