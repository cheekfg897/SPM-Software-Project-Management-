import { useId, useRef, useState } from 'react'

import { Button, Field, TextField } from '@/components/ui'
import type { FieldErrors } from '@/lib/api'

import type { OpeningPeriod } from '../api'
import { WEEKDAYS } from '../constants'
import type { Weekday } from '../constants'
import { periodFieldErrors, periodFieldName } from '../venueForm'
import type { PeriodErrors } from '../venueForm'

/** What a period added to the form starts as; the person changes it before saving. */
const NEW_PERIOD: OpeningPeriod = {
  open: { day: 'monday', time: '09:00' },
  close: { day: 'monday', time: '18:00' },
}

const SELECT_CLASSES =
  'border-line bg-surface text-ink focus:border-flare/70 aria-invalid:border-danger w-full rounded-xl border px-4 py-2.5 focus:outline-none'

interface DayFieldProps {
  label: string
  name: string
  day: Weekday
  errors: string[]
}

/** A labelled choice of weekday. Unlike SelectField, it has no empty choice. */
function DayField({ label, name, day, errors }: DayFieldProps) {
  return (
    <Field label={label} errors={errors}>
      {(control) => (
        <select {...control} name={name} defaultValue={day} className={SELECT_CLASSES}>
          {WEEKDAYS.map((weekday) => (
            <option key={weekday.value} value={weekday.value}>
              {weekday.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  )
}

interface PeriodRowProps {
  /** Where the period sits in the form, from 0, as the backend counts it in its messages. */
  index: number
  period: OpeningPeriod
  errors: PeriodErrors
  onRemove: () => void
}

/** One period's four controls, its messages, and a way to remove it. */
function PeriodRow({ index, period, errors, onRemove }: PeriodRowProps) {
  const errorsId = useId()
  const number = index + 1
  const hasPeriodErrors = errors.period.length > 0

  return (
    <fieldset
      aria-describedby={hasPeriodErrors ? errorsId : undefined}
      className="border-line/70 bg-surface/70 rounded-2xl border p-4"
    >
      {/* The legend must be the fieldset's first child to name the group. */}
      <legend className="text-ink float-left pt-2.5 text-sm font-medium">Period {number}</legend>
      <div className="flex justify-end">
        <Button variant="ghost" onClick={onRemove} aria-label={`Remove period ${number}`}>
          Remove
        </Button>
      </div>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <DayField
          label="Opens on"
          name={periodFieldName(index, 'open.day')}
          day={period.open.day}
          errors={errors.openDay}
        />
        <TextField
          label="Opens at"
          name={periodFieldName(index, 'open.time')}
          type="time"
          defaultValue={period.open.time}
          errors={errors.openTime}
        />
        <DayField
          label="Closes on"
          name={periodFieldName(index, 'close.day')}
          day={period.close.day}
          errors={errors.closeDay}
        />
        <TextField
          label="Closes at"
          name={periodFieldName(index, 'close.time')}
          type="time"
          defaultValue={period.close.time}
          errors={errors.closeTime}
        />
      </div>
      {hasPeriodErrors && (
        <ul id={errorsId} className="text-danger mt-3 space-y-0.5 text-sm">
          {errors.period.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
    </fieldset>
  )
}

interface OpeningHoursFieldsProps {
  /** The periods the form starts with. */
  initial: OpeningPeriod[]
  /** The backend's messages, keyed by field (`fieldErrors(error)`). */
  fieldErrors: FieldErrors
}

/**
 * The venue's weekly schedule as a list of periods to change, add to and remove (ADR-0008).
 * Each control is named the way the backend names its messages (`opening_hours.1.close.time`),
 * so each message shows under the control it is about.
 */
export function OpeningHoursFields({ initial, fieldErrors }: OpeningHoursFieldsProps) {
  // Each row keeps its key as rows are removed, so its controls keep what was typed into them.
  const [rows, setRows] = useState(() => initial.map((period, key) => ({ key, period })))
  const nextKey = useRef(initial.length)

  function addPeriod() {
    setRows([...rows, { key: nextKey.current, period: NEW_PERIOD }])
    nextKey.current += 1
  }

  function removePeriod(key: number) {
    setRows(rows.filter((row) => row.key !== key))
  }

  return (
    <div className="space-y-4">
      {rows.length === 0 && (
        <p className="text-ink-muted text-sm">With no periods, the venue is closed all week.</p>
      )}
      {rows.map((row, index) => (
        <PeriodRow
          key={row.key}
          index={index}
          period={row.period}
          errors={periodFieldErrors(fieldErrors, index)}
          onRemove={() => removePeriod(row.key)}
        />
      ))}
      <Button variant="secondary" onClick={addPeriod}>
        Add a period
      </Button>
    </div>
  )
}
