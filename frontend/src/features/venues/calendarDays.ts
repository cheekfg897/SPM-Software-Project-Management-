import { BUSINESS_UTC_OFFSET } from '@/config/time'

import type { CalendarEntry, CalendarRange } from './api'

/** The days a calendar shows, as the address holds them: `2026-11-10`, in business time. */
export interface DayRange {
  from: string
  to: string
}

/** One day of the calendar and the periods that touch it, in the backend's order. */
export interface CalendarDay {
  day: string
  entries: CalendarEntry[]
}

const DAYS_SHOWN_BY_DEFAULT = 7

/**
 * `date` moved by `days` whole days, e.g. "2026-11-30" + 1 is "2026-12-01". A date it can't read
 * (a hand-edited address) comes back as it is, for the backend to refuse.
 */
export function addDays(date: string, days: number): string {
  const moment = new Date(`${date}T00:00:00Z`)
  if (Number.isNaN(moment.getTime())) {
    return date
  }
  moment.setUTCDate(moment.getUTCDate() + days)
  return moment.toISOString().slice(0, 10)
}

/** The week from `today`: today and the six days after it (ADR-0058). */
export function weekFrom(today: string): DayRange {
  return { from: today, to: addDays(today, DAYS_SHOWN_BY_DEFAULT - 1) }
}

/**
 * The instants the calendar route takes for whole days: the first day's midnight and the
 * midnight after the last, without an offset, which the backend reads as business time.
 */
export function rangeQuery({ from, to }: DayRange): CalendarRange {
  return { range_start: `${from}T00:00:00`, range_end: `${addDays(to, 1)}T00:00:00` }
}

/** The moment a business day starts, in milliseconds. */
function startOf(day: string): number {
  return Date.parse(`${day}T00:00:00${BUSINESS_UTC_OFFSET}`)
}

/**
 * Every day from `from` to `to`, each with the periods that touch it (SCRUM-26 AC1). A period
 * that runs past midnight is under each day it touches. This only arranges what the backend
 * sent, which it already chose for these days: under each day the periods keep its order.
 */
export function calendarDays({ from, to }: DayRange, entries: CalendarEntry[]): CalendarDay[] {
  const days: CalendarDay[] = []
  for (let day = from; day <= to; day = addDays(day, 1)) {
    const dayStart = startOf(day)
    const dayEnd = startOf(addDays(day, 1))
    const touching = entries.filter(
      (entry) => Date.parse(entry.start_time) < dayEnd && Date.parse(entry.end_time) > dayStart,
    )
    days.push({ day, entries: touching })
  }
  return days
}
