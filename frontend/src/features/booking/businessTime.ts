import { BUSINESS_UTC_OFFSET } from '@/config/time'

/** `2026-11-10T09:30`, as a date-time input holds it, as `2026-11-10T09:30:00+08:00`. */
export function toBusinessTimeIso(inputValue: string): string {
  return `${inputValue}:00${BUSINESS_UTC_OFFSET}`
}
