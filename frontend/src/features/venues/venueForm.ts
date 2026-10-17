import { formText } from '@/features/auth/formText'
import type { FieldErrors } from '@/lib/api'

import type { OpeningPeriod, VenueDetails } from './api'
import type { Weekday } from './constants'

/** The part of a period a control holds, as the backend names it under `opening_hours.<n>`. */
export type PeriodPart = 'open.day' | 'open.time' | 'close.day' | 'close.time'

/** A period control's name, e.g. `opening_hours.0.open.day`, the key the backend's messages use. */
export function periodFieldName(index: number, part: PeriodPart): string {
  return `opening_hours.${index}.${part}`
}

/** Every value sent for a field that appears more than once: the layout checkboxes. */
function allTexts(form: FormData, name: string): string[] {
  return form.getAll(name).filter((value): value is string => typeof value === 'string')
}

/** A list typed one item per line. Empty lines are dropped; every other line goes as typed. */
function lines(form: FormData, name: string): string[] {
  return formText(form, name)
    .split('\n')
    .filter((line) => line.trim() !== '')
}

/** A day as its select holds it. */
function dayText(form: FormData, name: string): Weekday {
  // The day selects offer exactly the WEEKDAYS values, so what one holds is a Weekday.
  return formText(form, name) as Weekday
}

/** The periods as their controls hold them, first row first. */
function openingHours(form: FormData): OpeningPeriod[] {
  const periods: OpeningPeriod[] = []
  for (let index = 0; form.has(periodFieldName(index, 'open.day')); index += 1) {
    periods.push({
      open: {
        day: dayText(form, periodFieldName(index, 'open.day')),
        time: formText(form, periodFieldName(index, 'open.time')),
      },
      close: {
        day: dayText(form, periodFieldName(index, 'close.day')),
        time: formText(form, periodFieldName(index, 'close.time')),
      },
    })
  }
  return periods
}

/**
 * What the venue form sends, as the backend names it (ADR-0053). Every check is the backend's:
 * an empty capacity goes as null so it is refused, and an empty setup or turnaround time is left
 * out, so a new venue takes the standard time and a change keeps the venue's own.
 */
export function venueFromForm(form: FormData): VenueDetails {
  const capacity = formText(form, 'capacity')
  const details: VenueDetails = {
    name: formText(form, 'name'),
    location: formText(form, 'location'),
    capacity: capacity === '' ? null : Number(capacity),
    facilities: lines(form, 'facilities'),
    accessibility_features: lines(form, 'accessibility_features'),
    supported_layouts: allTexts(form, 'supported_layouts'),
    opening_hours: openingHours(form),
  }
  const setup = formText(form, 'setup_minutes')
  if (setup !== '') {
    details.setup_minutes = Number(setup)
  }
  const turnaround = formText(form, 'turnaround_minutes')
  if (turnaround !== '') {
    details.turnaround_minutes = Number(turnaround)
  }
  return details
}

/**
 * The backend's messages for a list field: the list's own (too many items), then each refused
 * item's, which it keys by position (`facilities.1`), numbered here from 1 for people.
 */
export function listFieldErrors(fieldErrors: FieldErrors, field: string): string[] {
  const messages = [...(fieldErrors[field] ?? [])]
  const itemPrefix = `${field}.`
  for (const [key, itemMessages] of Object.entries(fieldErrors)) {
    if (key.startsWith(itemPrefix)) {
      const itemNumber = Number(key.slice(itemPrefix.length)) + 1
      for (const message of itemMessages) {
        messages.push(`Item ${itemNumber}: ${message}`)
      }
    }
  }
  return messages
}

/** The backend's messages for one period, for each of its controls. */
export interface PeriodErrors {
  openDay: string[]
  openTime: string[]
  closeDay: string[]
  /** The close time's own, then the period's rule, which the backend files under `close`. */
  closeTime: string[]
  /** About the period as a whole: that it overlaps another. */
  period: string[]
}

export function periodFieldErrors(fieldErrors: FieldErrors, index: number): PeriodErrors {
  const path = `opening_hours.${index}`
  return {
    openDay: fieldErrors[periodFieldName(index, 'open.day')] ?? [],
    openTime: fieldErrors[periodFieldName(index, 'open.time')] ?? [],
    closeDay: fieldErrors[periodFieldName(index, 'close.day')] ?? [],
    closeTime: [
      ...(fieldErrors[periodFieldName(index, 'close.time')] ?? []),
      ...(fieldErrors[`${path}.close`] ?? []),
    ],
    period: fieldErrors[path] ?? [],
  }
}
