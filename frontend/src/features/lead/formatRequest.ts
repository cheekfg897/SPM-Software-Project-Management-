import { BUSINESS_TIME_ZONE } from '@/config/time'

/**
 * Display formats for the queue's fields. The proposed date and the start and end times arrive
 * as plain business-time values (`2026-11-12`, `09:00:00`) with no offset, so they are read as
 * UTC and shown as UTC: the clock reading is what is shown, with no time zone moving it.
 * The submission time carries an offset and is shown in business time.
 */

const LOCALE = 'en-SG'

const PLAIN_DATE_FORMAT = new Intl.DateTimeFormat(LOCALE, {
  timeZone: 'UTC',
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})
const PLAIN_TIME_FORMAT = new Intl.DateTimeFormat(LOCALE, {
  timeZone: 'UTC',
  hour: 'numeric',
  minute: '2-digit',
})
const SUBMITTED_FORMAT = new Intl.DateTimeFormat(LOCALE, {
  timeZone: BUSINESS_TIME_ZONE,
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

/** e.g. "12 Nov 2026" from "2026-11-12". */
export function formatProposedDate(date: string): string {
  return PLAIN_DATE_FORMAT.format(new Date(date))
}

/** e.g. "9:00 am – 5:00 pm" from "09:00:00" and "17:00:00". */
export function formatProposedTimes(startTime: string, endTime: string): string {
  const start = PLAIN_TIME_FORMAT.format(new Date(`1970-01-01T${startTime}Z`))
  const end = PLAIN_TIME_FORMAT.format(new Date(`1970-01-01T${endTime}Z`))
  return `${start} – ${end}`
}

/** e.g. "1 Oct 2026, 9:30 am" from "2026-10-01T09:30:00+08:00". */
export function formatSubmittedAt(submittedAt: string): string {
  return SUBMITTED_FORMAT.format(new Date(submittedAt))
}
