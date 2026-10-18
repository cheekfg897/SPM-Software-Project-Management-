import type { FieldErrors } from '@/lib/api'

/**
 * The backend's messages for one list field, to show under its box: the list's own (too many
 * items), then each bad item's, which it keys by place (`required_facilities.1`). Items are
 * numbered from 1 and counted without the empty lines the form drops (ADR-0073).
 */
export function listMessages(fieldErrors: FieldErrors, name: string): string[] {
  const messages = [...(fieldErrors[name] ?? [])]
  const itemPrefix = `${name}.`
  for (const [field, itemMessages] of Object.entries(fieldErrors)) {
    if (!field.startsWith(itemPrefix)) {
      continue
    }
    const itemNumber = Number(field.slice(itemPrefix.length)) + 1
    for (const message of itemMessages) {
      messages.push(`Item ${itemNumber}: ${message}`)
    }
  }
  return messages
}
