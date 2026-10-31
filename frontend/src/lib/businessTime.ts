import { BUSINESS_UTC_OFFSET } from '@/config/time'

/** `2026-11-10T09:30`, as a date-time input holds it, as `2026-11-10T09:30:00+08:00`. */
export function toBusinessTimeIso(inputValue: string): string {
  return `${inputValue}:00${BUSINESS_UTC_OFFSET}`
}

/** A saved time of day (`19:00:00`) as a time input holds it, to the minute (`19:00`). */
export function toTimeInputValue(savedTime: string): string {
  return savedTime.slice(0, 5)
}
