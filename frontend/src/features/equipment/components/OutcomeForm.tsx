import { useId, useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextAreaField, TextField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { EquipmentLine, EquipmentOutcomeBody } from '../api'
import { useRecordEquipmentOutcome } from '../hooks'

/** What the outcome form holds: each field as typed. */
interface OutcomeValues {
  provided_quantity: string
  note: string
}

/** The line's current outcome, ready to revise, or empty boxes when it has none. */
function valuesOfOutcome(line: EquipmentLine): OutcomeValues {
  return {
    provided_quantity: line.provided_quantity === null ? '' : String(line.provided_quantity),
    note: line.outcome_note ?? '',
  }
}

/** What saving sends. A blank field is left out, so the backend says what is missing (ADR-0077). */
function outcomeBody(values: OutcomeValues): EquipmentOutcomeBody {
  const body: EquipmentOutcomeBody = {}
  if (values.provided_quantity !== '') {
    body.provided_quantity = Number(values.provided_quantity)
  }
  if (values.note !== '') {
    body.note = values.note
  }
  return body
}

interface OutcomeFormProps {
  reference: string
  line: EquipmentLine
  lineName: string
  /** Close the form: once the outcome is saved, or on cancel. */
  onDone: () => void
}

/**
 * Record or revise how much of one line Technical Support will provide (SCRUM-48 AC1-AC3, AC6).
 * Whether a note is needed, and how many may be provided, is the backend's to say.
 */
export function OutcomeForm({ reference, line, lineName, onDone }: OutcomeFormProps) {
  const headingId = useId()
  const [values, setValues] = useState(() => valuesOfOutcome(line))
  const record = useRecordEquipmentOutcome(reference)
  const fieldErrors = fieldErrorsOf(record.error)
  const hasFieldErrors = Object.keys(fieldErrors).length > 0

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    record.mutate({ lineId: line.id, body: outcomeBody(values) }, { onSuccess: onDone })
  }

  return (
    <form
      aria-labelledby={headingId}
      onSubmit={handleSubmit}
      className="border-line/70 bg-surface/70 space-y-4 rounded-2xl border p-5"
    >
      <h3 id={headingId} className="font-display text-lg font-semibold tracking-tight">
        Outcome for {lineName}
      </h3>
      {!hasFieldErrors && <ErrorAlert error={record.error} />}
      <TextField
        label="Quantity provided"
        name="provided_quantity"
        type="number"
        inputMode="numeric"
        hint={`${line.quantity} asked for.`}
        value={values.provided_quantity}
        onChange={(event) => setValues({ ...values, provided_quantity: event.target.value })}
        errors={fieldErrors.provided_quantity}
      />
      <TextAreaField
        label="Note for the coordinator"
        name="note"
        hint="Why any of it can't be provided, and any alternative they could use."
        value={values.note}
        onChange={(event) => setValues({ ...values, note: event.target.value })}
        errors={fieldErrors.note}
      />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" isPending={record.isPending}>
          Save outcome
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
