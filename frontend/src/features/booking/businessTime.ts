/**
 * Business time (BUSINESS_TIME_ZONE, Asia/Singapore) is a fixed UTC+8 all year, which is what
 * lets a date-time input's value be turned into an ISO date-time with an offset by appending it.
 */
const BUSINESS_UTC_OFFSET = '+08:00'

/** `2026-11-10T09:30`, as a date-time input holds it, as `2026-11-10T09:30:00+08:00`. */
export function toBusinessTimeIso(inputValue: string): string {
  return `${inputValue}:00${BUSINESS_UTC_OFFSET}`
}
