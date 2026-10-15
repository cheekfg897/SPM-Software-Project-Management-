import type { ReactNode } from 'react'

import { formatShortDate, formatWeekday } from '@/lib/formatDate'

import { groupByDay } from '../groupByDay'

interface DayTimelineProps<T extends { starts_at: string }> {
  events: T[]
  /** A key for each event, unique among the events shown. */
  keyOf: (event: T) => number
  /** The card that shows one event. */
  renderEvent: (event: T) => ReactNode
}

/**
 * Events under a heading per day, on a timeline, in the order the backend sent. The catalogue
 * and an Attendee's own events both draw their cards on it.
 */
export function DayTimeline<T extends { starts_at: string }>({
  events,
  keyOf,
  renderEvent,
}: DayTimelineProps<T>) {
  return (
    <ol className="space-y-10">
      {groupByDay(events).map((group, index) => {
        const firstStart = group.events[0].starts_at
        return (
          // minmax(0, …) lets the column shrink to the screen; a plain grid or 1fr column
          // grows to fit text that won't wrap, such as a long venue name, and the page
          // then scrolls sideways on a phone.
          <li
            key={`${index}-${group.day}`}
            className="grid grid-cols-1 gap-4 md:grid-cols-[10rem_minmax(0,1fr)]"
          >
            <h2 className="flex items-baseline gap-2 md:sticky md:top-24 md:flex-col md:gap-0 md:self-start">
              <span className="text-ink-muted text-sm">{formatWeekday(firstStart)}</span>{' '}
              <span className="font-display text-ink text-lg font-semibold">
                {formatShortDate(firstStart)}
              </span>
            </h2>
            <ul className="border-line space-y-4 border-l border-dashed pl-5 md:pl-6">
              {group.events.map((event) => (
                <li key={keyOf(event)}>{renderEvent(event)}</li>
              ))}
            </ul>
          </li>
        )
      })}
    </ol>
  )
}
