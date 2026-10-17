import { DISPLAY_LOCALE } from '@/config/time'
import { VENUE_LAYOUTS } from '@/config/venueLayouts'
import type { VenueLayout } from '@/config/venueLayouts'

import type { OpeningPeriod } from './api'
import { WEEKDAYS } from './constants'
import type { Weekday } from './constants'

/**
 * Opening hours are wall-clock times with no date (ADR-0008), so they are written as they are:
 * read as UTC and written in UTC, no time zone can move them.
 */
const CLOCK_FORMAT = new Intl.DateTimeFormat(DISPLAY_LOCALE, {
  timeZone: 'UTC',
  hour: 'numeric',
  minute: '2-digit',
})

/** e.g. "18:30" as "6:30 pm", the way the rest of the app writes times. */
export function formatClock(time: string): string {
  return CLOCK_FORMAT.format(new Date(`1970-01-01T${time}:00Z`))
}

export function weekdayLabel(day: Weekday): string {
  return WEEKDAYS.find((weekday) => weekday.value === day)?.label ?? day
}

export function layoutLabel(layout: VenueLayout): string {
  return VENUE_LAYOUTS.find((option) => option.value === layout)?.label ?? layout
}

/** e.g. "8:00 am – 10:00 pm", or "6:00 pm – Sunday 2:00 am" for a period past midnight. */
export function formatPeriodHours({ open, close }: OpeningPeriod): string {
  const closes = formatClock(close.time)
  const closing = close.day === open.day ? closes : `${weekdayLabel(close.day)} ${closes}`
  return `${formatClock(open.time)} – ${closing}`
}

/** A setup or turnaround time (SCRUM-67): "None", "1 minute", "45 minutes". */
export function formatMinutes(minutes: number): string {
  if (minutes === 0) {
    return 'None'
  }
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}
