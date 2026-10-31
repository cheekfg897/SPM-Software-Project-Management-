import { BUSINESS_UTC_OFFSET } from '@/config/time'

/**
 * Instants written in business time, as the backend writes them, for the mocks that answer for
 * it: the venue module's blocks and calendar, and its booking requests.
 */

/** Business time is UTC+8 all year (BUSINESS_UTC_OFFSET), as milliseconds. */
const BUSINESS_OFFSET_MS = 8 * 60 * 60_000

/** An instant as the backend sends it, in business time: "2026-11-16T09:00:00+08:00". */
export function businessIso(instant: number): string {
  return `${new Date(instant + BUSINESS_OFFSET_MS).toISOString().slice(0, 19)}${BUSINESS_UTC_OFFSET}`
}

/** An instant as the backend's messages write it, in business time: "2026-11-16 09:00". */
export function noticeTime(instant: number): string {
  return new Date(instant + BUSINESS_OFFSET_MS).toISOString().slice(0, 16).replace('T', ' ')
}
