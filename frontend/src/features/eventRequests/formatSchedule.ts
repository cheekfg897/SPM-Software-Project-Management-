import type { EventRequest } from './api'

/**
 * When an event request is on, for its row in a list. A request's dates and times are business
 * time as written, with no offset (ADR-0002), so they are read just as they are: building them
 * as UTC moments and formatting them in UTC keeps 12 Nov at 9:00 am, wherever the viewer is.
 */

const LOCALE = 'en-SG'
const DAY_FORMAT = new Intl.DateTimeFormat(LOCALE, {
  timeZone: 'UTC',
  weekday: 'short',
  day: 'numeric',
  month: 'short',
})
const TIME_FORMAT = new Intl.DateTimeFormat(LOCALE, {
  timeZone: 'UTC',
  hour: 'numeric',
  minute: '2-digit',
})
const NO_DATE_YET = 'Date to be set'

type Schedule = Pick<EventRequest, 'proposed_date' | 'end_date' | 'start_time' | 'end_time'>

/** e.g. "Thu, 12 Nov" for "2026-11-12". */
function formatDay(date: string): string {
  return DAY_FORMAT.format(new Date(`${date}T00:00:00Z`))
}

/** e.g. "9:00 am" for "09:00:00". */
function formatTime(time: string): string {
  return TIME_FORMAT.format(new Date(`1970-01-01T${time}Z`))
}

/**
 * e.g. "Thu, 12 Nov · 9:00 am – 5:30 pm", or both days when the event ends on a later one. A
 * draft may not have its date or times yet, so it shows what it has.
 */
export function formatSchedule(schedule: Schedule): string {
  const { proposed_date: startDate, start_time: startTime, end_time: endTime } = schedule
  if (startDate === null) {
    return NO_DATE_YET
  }
  const startDay = formatDay(startDate)
  if (startTime === null || endTime === null) {
    return startDay
  }

  const endDate = schedule.end_date ?? startDate
  const start = formatTime(startTime)
  const end = formatTime(endTime)
  if (endDate === startDate) {
    return `${startDay} · ${start} – ${end}`
  }
  return `${startDay}, ${start} – ${formatDay(endDate)}, ${end}`
}
