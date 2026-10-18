import { formatDateTime } from './formatDate'

/**
 * e.g. "Decided by Marcus Tan, 29 Sept, 3:20 pm". The backend sends no name for someone whose
 * account is gone (events/services.py `_actor_name`), and then it's only when.
 */
export function attributed(action: string, name: string | null, at: string): string {
  const when = formatDateTime(at)
  if (name === null) {
    return `${action} ${when}`
  }
  return `${action} by ${name}, ${when}`
}
