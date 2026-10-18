import { useState } from 'react'
import type { FormEvent } from 'react'
import type { UseMutationResult } from '@tanstack/react-query'

import { Button, ErrorAlert, SelectField, TextAreaField } from '@/components/ui'
import { PREPARATION_STATUS_OPTIONS } from '@/config/preparation'
import type { Preparation, PreparationUpdate } from '@/config/preparation'
import { fieldErrorsOf } from '@/lib/api'

interface PreparationFormProps {
  /** What is being prepared, e.g. a booking's purpose, so each field says which it is for. */
  subject: string
  /** What is recorded now; the form starts from it. */
  current: Preparation
  /** Sends the update. The list the booking or reservation came from is read again after. */
  mutation: UseMutationResult<unknown, Error, PreparationUpdate>
}

/** The update to send: empty notes are left out, which clears them (ADR-0049 decision 4). */
function updateFrom(status: string, notes: string): PreparationUpdate {
  if (notes === '') {
    return { status }
  }
  return { status, notes }
}

/**
 * Records a preparation status and notes (SCRUM-84, SCRUM-85). The backend decides what is
 * allowed (the safety approval, blank notes, their length), and its refusal shows as it comes.
 */
export function PreparationForm({ subject, current, mutation }: PreparationFormProps) {
  const [status, setStatus] = useState<string>(current.preparation_status)
  const [notes, setNotes] = useState(current.preparation_notes ?? '')
  const fieldErrors = fieldErrorsOf(mutation.error)
  const hasFieldErrors = Object.keys(fieldErrors).length > 0

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate(updateFrom(status, notes))
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {!hasFieldErrors && <ErrorAlert error={mutation.error} />}
      <SelectField
        label={`Preparation status for ${subject}`}
        name="status"
        options={PREPARATION_STATUS_OPTIONS}
        emptyLabel="Choose a status"
        value={status}
        onChange={(event) => setStatus(event.target.value)}
        errors={fieldErrors.status}
      />
      <TextAreaField
        label={`Preparation notes for ${subject}`}
        name="notes"
        hint="Leave empty to clear the notes."
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        errors={fieldErrors.notes}
      />
      <Button
        type="submit"
        isPending={mutation.isPending}
        aria-label={`Save preparation for ${subject}`}
      >
        Save preparation
      </Button>
      {mutation.isSuccess && (
        <p role="status" className="text-success text-sm">
          Preparation saved.
        </p>
      )}
    </form>
  )
}
