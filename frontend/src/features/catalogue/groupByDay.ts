import { businessDate } from '@/lib/formatDate'

export interface DayGroup<T> {
  /** The business date, e.g. "2026-10-05". */
  day: string
  /** Never empty, so the first event can name the day. */
  events: [T, ...T[]]
}

/**
 * Put neighbouring events on the same business day under one heading.
 *
 * This only arranges the page the backend returned: it keeps the backend's order, and never
 * filters or sorts. A day that turns up again later simply starts a new group.
 */
export function groupByDay<T extends { starts_at: string }>(events: T[]): DayGroup<T>[] {
  const groups: DayGroup<T>[] = []
  for (const event of events) {
    const day = businessDate(event.starts_at)
    const lastGroup = groups[groups.length - 1]
    if (lastGroup !== undefined && lastGroup.day === day) {
      lastGroup.events.push(event)
    } else {
      groups.push({ day, events: [event] })
    }
  }
  return groups
}
