import type { FormEvent } from 'react'

import { Button, ErrorAlert, SelectField, TextField } from '@/components/ui'
import { formText } from '@/features/auth/formText'
import { fieldErrorsOf } from '@/lib/api'

import type { ArrangementChange, BookingRequest } from '../api'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { useChangeArrangement } from '../hooks'

/**
 * The change for the backend. An empty layout is sent as null, which clears it; an empty
 * occupancy or justification is left out, so the backend keeps what it has.
 */
function changeFrom(form: FormData): ArrangementChange {
  const layout = formText(form, 'required_layout')
  const change: ArrangementChange = {
    purpose: formText(form, 'purpose'),
    required_layout: layout === '' ? null : layout,
  }
  const occupancy = formText(form, 'expected_occupancy')
  if (occupancy !== '') {
    change.expected_occupancy = Number(occupancy)
  }
  const justification = formText(form, 'justification')
  if (justification !== '') {
    change.justification = justification
  }
  return change
}

interface ChangeArrangementFormProps {
  reference: string
  arrangement: BookingRequest
  /** Called when the coordinator closes the form, and once the change is saved. */
  onClose: () => void
}

/**
 * Change what an arrangement asks for (SCRUM-93). The venue and the period are not here: to
 * move either, the coordinator withdraws the arrangement and raises another.
 */
export function ChangeArrangementForm({
  reference,
  arrangement,
  onClose,
}: ChangeArrangementFormProps) {
  const change = useChangeArrangement(reference, arrangement.id)
  const fieldErrors = fieldErrorsOf(change.error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    change.mutate(changeFrom(new FormData(event.currentTarget)), { onSuccess: onClose })
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={`Change ${arrangement.purpose}`}
      className="border-line mt-4 space-y-4 border-t pt-4"
    >
      <ErrorAlert error={change.error} />
      <TextField
        label="Purpose"
        name="purpose"
        required
        defaultValue={arrangement.purpose}
        errors={fieldErrors.purpose}
      />
      <TextField
        label="Expected occupancy"
        name="expected_occupancy"
        type="number"
        min={1}
        defaultValue={arrangement.expected_occupancy}
        errors={fieldErrors.expected_occupancy}
      />
      <SelectField
        label="Required layout"
        name="required_layout"
        options={LAYOUT_OPTIONS}
        defaultValue={arrangement.required_layout ?? ''}
        errors={fieldErrors.required_layout}
      />
      <TextField
        label="Justification"
        name="justification"
        defaultValue={arrangement.justification ?? ''}
        hint="Needed when the venue does not suit this request's occupancy and layout."
        errors={fieldErrors.justification}
      />
      <div className="flex gap-3">
        <Button type="submit" isPending={change.isPending}>
          Save changes
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
    </form>
  )
}
