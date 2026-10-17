import { formText } from '@/features/auth/formText'

import type { EquipmentTypeInput } from './api'

/** A number typed into the form, or null when the field was left empty. */
function numberOrNull(text: string): number | null {
  return text === '' ? null : Number(text)
}

function textOrNull(text: string): string | null {
  return text === '' ? null : text
}

/**
 * The equipment type form as the backend wants it (ADR-0066). Every field is sent, so an edit
 * replaces the whole type. An empty quantity, venue or store goes as null, so the backend refuses
 * a missing quantity or place instead of keeping the old one; every check is the backend's.
 */
export function inputFromForm(form: FormData): EquipmentTypeInput {
  return {
    name: formText(form, 'name'),
    description: formText(form, 'description'),
    total_quantity: numberOrNull(formText(form, 'total_quantity')),
    venue_id: numberOrNull(formText(form, 'venue_id')),
    store_name: textOrNull(formText(form, 'store_name')),
  }
}
