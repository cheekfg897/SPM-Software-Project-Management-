import { useRef, useState } from 'react'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import { useFocusFirstError } from '@/features/eventRequests/useFocusFirstError'
import { fieldErrorsOf } from '@/lib/api'

import type { SafetyChecklist } from '../api'
import { CHECKLIST, OUTCOME_ACTION_LABELS, SAFETY_OUTCOME } from '../constants'
import type { SafetyOutcome } from '../constants'
import { useRecordSafetyOutcome } from '../hooks'

/** The three outcomes in SCRUM-98 AC1's order; Approve is the main action. */
const OUTCOME_BUTTONS = [
  { outcome: SAFETY_OUTCOME.APPROVED, variant: 'primary' },
  { outcome: SAFETY_OUTCOME.REJECTED, variant: 'secondary' },
  { outcome: SAFETY_OUTCOME.CHANGES_REQUESTED, variant: 'secondary' },
] as const

const EMPTY_CHECKLIST: SafetyChecklist = {
  attendance_vs_capacity: '',
  venue_layout: '',
  emergency_access: '',
  accessibility: '',
  equipment_placement: '',
  crowd_movement: '',
  venue_restrictions: '',
}

interface SafetyOutcomeFormProps {
  reference: string
  /** The event's name, so the form and its buttons say which event they belong to. */
  name: string
}

/**
 * The safety check for one event (SCRUM-98): a note on each checklist item, a reason, and one
 * button per outcome. What is required, and when, is the backend's to say: its messages appear
 * under the fields they are about, and any other refusal above the buttons.
 */
export function SafetyOutcomeForm({ reference, name }: SafetyOutcomeFormProps) {
  const [notes, setNotes] = useState<SafetyChecklist>(EMPTY_CHECKLIST)
  const [reason, setReason] = useState('')
  const record = useRecordSafetyOutcome()
  const formRef = useRef<HTMLFormElement>(null)
  useFocusFirstError(formRef, record.error)
  const fieldErrors = fieldErrorsOf(record.error)
  const hasFieldErrors = Object.keys(fieldErrors).length > 0

  function send(outcome: SafetyOutcome) {
    const input = { reference, outcome, checklist: notes }
    record.mutate(reason === '' ? input : { ...input, reason })
  }

  return (
    <form ref={formRef} aria-label={`Safety check for ${name}`} className="mt-5 space-y-5">
      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="text-ink mb-3 text-sm font-semibold">Checklist</legend>
        {CHECKLIST.map(({ item, label, hint }) => (
          <TextAreaField
            key={item}
            label={label}
            name={item}
            rows={2}
            hint={hint}
            value={notes[item]}
            onChange={(event) => setNotes({ ...notes, [item]: event.target.value })}
            errors={fieldErrors[`checklist.${item}`]}
          />
        ))}
      </fieldset>
      <TextAreaField
        label="Reason"
        name="reason"
        rows={2}
        hint="Required to reject or request changes."
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        errors={fieldErrors.reason}
      />
      {!hasFieldErrors && <ErrorAlert error={record.error} />}
      <div className="flex flex-wrap gap-3">
        {OUTCOME_BUTTONS.map(({ outcome, variant }) => (
          <Button
            key={outcome}
            variant={variant}
            isPending={record.isPending}
            aria-label={`${OUTCOME_ACTION_LABELS[outcome]} ${name}`}
            onClick={() => send(outcome)}
          >
            {OUTCOME_ACTION_LABELS[outcome]}
          </Button>
        ))}
      </div>
    </form>
  )
}
