import { useRef, useState } from 'react'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import { useFocusFirstError } from '@/features/eventRequests/useFocusFirstError'
import { fieldErrorsOf } from '@/lib/api'

import type { AwaitingSafetyReview, RecordSafetyOutcomeInput, SafetyChecklist } from '../api'
import { CHECKLIST, OUTCOME_ACTION_LABELS, SAFETY_OUTCOME } from '../constants'
import type { SafetyOutcome } from '../constants'
import { useRecordSafetyOutcome } from '../hooks'

import { ReworkChoices } from './ReworkChoices'
import type { Rework } from './ReworkChoices'

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

const NOTHING_TO_REWORK: Rework = { flagged_arrangement_ids: [], reopened_line_ids: [] }

/**
 * What to send for `outcome`: the checklist, the reason when one was typed, and what was ticked to
 * rework, each list left out when nothing on it is ticked (SCRUM-99 AC2).
 */
function outcomeInput(
  reference: string,
  outcome: SafetyOutcome,
  { notes, reason, rework }: { notes: SafetyChecklist; reason: string; rework: Rework },
): RecordSafetyOutcomeInput {
  const input: RecordSafetyOutcomeInput = { reference, outcome, checklist: notes }
  if (reason !== '') {
    input.reason = reason
  }
  if (rework.flagged_arrangement_ids.length > 0) {
    input.flagged_arrangement_ids = rework.flagged_arrangement_ids
  }
  if (rework.reopened_line_ids.length > 0) {
    input.reopened_line_ids = rework.reopened_line_ids
  }
  return input
}

/**
 * The safety check for one event (SCRUM-98): a note on each checklist item, a reason, what to
 * rework (SCRUM-99), and one button per outcome. What is required, and when, is the backend's to
 * say: its messages appear under the fields they are about, and any other refusal above the
 * buttons.
 */
export function SafetyOutcomeForm({ awaiting }: { awaiting: AwaitingSafetyReview }) {
  const { reference, name } = awaiting.event
  const [notes, setNotes] = useState<SafetyChecklist>(EMPTY_CHECKLIST)
  const [reason, setReason] = useState('')
  const [rework, setRework] = useState<Rework>(NOTHING_TO_REWORK)
  const record = useRecordSafetyOutcome()
  const formRef = useRef<HTMLFormElement>(null)
  useFocusFirstError(formRef, record.error)
  const fieldErrors = fieldErrorsOf(record.error)
  const hasFieldErrors = Object.keys(fieldErrors).length > 0
  const reworkErrors = [
    ...(fieldErrors.flagged_arrangement_ids ?? []),
    ...(fieldErrors.reopened_line_ids ?? []),
  ]

  function send(outcome: SafetyOutcome) {
    record.mutate(outcomeInput(reference, outcome, { notes, reason, rework }))
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
      <ReworkChoices
        venues={awaiting.venues}
        equipment={awaiting.equipment}
        rework={rework}
        onChange={setRework}
        errors={reworkErrors}
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
