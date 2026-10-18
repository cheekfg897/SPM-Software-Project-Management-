import { useId } from 'react'
import type { FormEvent } from 'react'
import { useSearchParams } from 'react-router'

import { Button, ErrorAlert, Spinner, TextField } from '@/components/ui'
import { formText } from '@/features/auth/formText'
import { fieldErrorsOf } from '@/lib/api'
import { businessDate, formatShortDate, formatTimeRange, formatWeekday } from '@/lib/formatDate'

import type { CalendarEntry, CalendarEntryKind } from '../api'
import { calendarDays, rangeQuery, weekFrom } from '../calendarDays'
import type { CalendarDay, DayRange } from '../calendarDays'
import { useVenueCalendar } from '../hooks'

import { VenueSection } from './VenueSection'

const FROM_PARAM = 'from'
const TO_PARAM = 'to'

/** How each kind of period reads, coloured by what it means. */
const KIND_STYLES: Record<CalendarEntryKind, { label: string; tone: string }> = {
  confirmed_booking: { label: 'Booked', tone: 'border-flare/30 bg-flare/10 text-flare' },
  tentative_hold: { label: 'Tentative', tone: 'border-nebula/50 bg-nebula/15 text-ink' },
  block: { label: 'Blocked', tone: 'border-danger/30 bg-danger/10 text-danger' },
}

/** Midday on a business day, so its name and date are written for that day in business time. */
function middayOf(day: string): string {
  return `${day}T12:00:00+08:00`
}

/** The days in the address, or the week from today when it names none (ADR-0068). */
function useDayRange(): [DayRange, (range: DayRange) => void] {
  const [searchParams, setSearchParams] = useSearchParams()
  const week = weekFrom(businessDate(new Date().toISOString()))
  const range = {
    from: searchParams.get(FROM_PARAM) ?? week.from,
    to: searchParams.get(TO_PARAM) ?? week.to,
  }
  function setRange({ from, to }: DayRange) {
    setSearchParams({ [FROM_PARAM]: from, [TO_PARAM]: to })
  }
  return [range, setRange]
}

/** One unavailable period: its kind, when, why, and for a booking its event's own times. */
function PeriodRow({ entry }: { entry: CalendarEntry }) {
  const { label, tone } = KIND_STYLES[entry.kind]
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
      <span
        className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${tone}`}
      >
        {label}
      </span>{' '}
      <span className="text-ink">{formatTimeRange(entry.start_time, entry.end_time)}</span>{' '}
      <span className="text-ink-muted">{entry.reason}</span>
      {entry.event_start !== null && entry.event_end !== null && (
        <>
          {' '}
          <span className="text-ink-faint">
            Event {formatTimeRange(entry.event_start, entry.event_end)}
          </span>
        </>
      )}
    </li>
  )
}

/** One day: its name and date, then each period that touches it, or that there are none. */
function DayRow({ day, entries }: CalendarDay) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="grid gap-2 md:grid-cols-[10rem_minmax(0,1fr)]">
      <h3 id={headingId} className="flex items-baseline gap-2 md:flex-col md:gap-0">
        <span className="text-ink-muted text-sm">{formatWeekday(middayOf(day))}</span>{' '}
        <span className="font-display text-ink text-lg font-semibold">
          {formatShortDate(middayOf(day))}
        </span>
      </h3>
      {entries.length === 0 ? (
        <p className="text-ink-faint text-sm">Nothing booked or blocked.</p>
      ) : (
        <ul className="border-line space-y-2 border-l border-dashed pl-5">
          {entries.map((entry) => (
            <PeriodRow key={`${entry.kind}-${entry.start_time}-${entry.end_time}`} entry={entry} />
          ))}
        </ul>
      )}
    </section>
  )
}

/**
 * The venue's availability over the days chosen (SCRUM-26): every day with its bookings,
 * tentative holds and blocks, each reason as much as the viewer's role is told (AC3). The days
 * live in the address, so a shared link shows the same ones (ADR-0068).
 */
export function VenueCalendar({ venueId }: { venueId: number }) {
  const [range, setRange] = useDayRange()
  const calendar = useVenueCalendar(venueId, rangeQuery(range))
  const fieldErrors = fieldErrorsOf(calendar.error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setRange({ from: formText(form, FROM_PARAM), to: formText(form, TO_PARAM) })
  }

  return (
    <VenueSection
      title="Availability"
      description="What holds the venue on each day: bookings, with their setup and turnaround, and blocks."
    >
      {/* Keyed by the days, so going back in history puts them back in the fields. */}
      <form
        key={`${range.from}-${range.to}`}
        onSubmit={handleSubmit}
        className="flex flex-wrap items-start gap-4"
      >
        <TextField
          label="From"
          name={FROM_PARAM}
          type="date"
          defaultValue={range.from}
          errors={fieldErrors.range_start}
        />
        <TextField
          label="To"
          name={TO_PARAM}
          type="date"
          defaultValue={range.to}
          errors={fieldErrors.range_end}
        />
        <Button type="submit" variant="secondary" className="sm:mt-7">
          Show these days
        </Button>
      </form>
      <div className="mt-8">
        {calendar.isPending && (
          <p role="status" className="text-ink-muted flex items-center gap-3">
            <Spinner />
            Loading availability…
          </p>
        )}
        <ErrorAlert error={calendar.error} />
        {calendar.isSuccess && (
          <div className="space-y-6">
            {calendarDays(range, calendar.data).map(({ day, entries }) => (
              <DayRow key={day} day={day} entries={entries} />
            ))}
          </div>
        )}
      </div>
    </VenueSection>
  )
}
