import { BUSINESS_TIME_ZONE, DISPLAY_LOCALE } from '@/config/time'

/**
 * Display formats for the backend's date-times, always in business time so a visitor abroad
 * sees the times the event is actually on.
 */

// en-CA writes dates as YYYY-MM-DD, which sorts and compares as text.
const DATE_KEY_FORMAT = new Intl.DateTimeFormat('en-CA', {
  timeZone: BUSINESS_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})
const WEEKDAY_FORMAT = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: BUSINESS_TIME_ZONE,
  weekday: 'long',
})
const SHORT_WEEKDAY_FORMAT = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: BUSINESS_TIME_ZONE,
  weekday: 'short',
})
const SHORT_DATE_FORMAT = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: BUSINESS_TIME_ZONE,
  day: 'numeric',
  month: 'short',
})
const TIME_FORMAT = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: BUSINESS_TIME_ZONE,
  hour: 'numeric',
  minute: '2-digit',
})

/** The business date a moment falls on, e.g. "2026-10-05". */
export function businessDate(isoDateTime: string): string {
  return DATE_KEY_FORMAT.format(new Date(isoDateTime))
}

/** e.g. "Monday" */
export function formatWeekday(isoDateTime: string): string {
  return WEEKDAY_FORMAT.format(new Date(isoDateTime))
}

/** e.g. "5 Oct" */
export function formatShortDate(isoDateTime: string): string {
  return SHORT_DATE_FORMAT.format(new Date(isoDateTime))
}

/** e.g. "7:30 pm – 10:00 pm", or "9:00 pm – Sat 12:00 am" when the event ends on a later day. */
export function formatTimeRange(startsAt: string, endsAt: string): string {
  const start = TIME_FORMAT.format(new Date(startsAt))
  const end = TIME_FORMAT.format(new Date(endsAt))
  if (businessDate(startsAt) === businessDate(endsAt)) {
    return `${start} – ${end}`
  }
  return `${start} – ${SHORT_WEEKDAY_FORMAT.format(new Date(endsAt))} ${end}`
}
