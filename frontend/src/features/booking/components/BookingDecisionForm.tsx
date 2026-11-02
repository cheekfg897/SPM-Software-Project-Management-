import { useState } from 'react'
import type { ChangeEvent } from 'react'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'
import { toBusinessTimeIso } from '@/lib/businessTime'

import type { BookingDecision } from '../api'
import { useDecideBookingRequest } from '../hooks'

interface BookingDecisionFormProps {
  requestId: number
  /** The request's purpose, so each field and button says which request it belongs to. */
  purpose: string
}

/** What Venue Staff typed: the reason, and any alternative they suggest (SCRUM-70). */
interface DecisionFields {
  reason: string
  venueId: string
  startsAt: string
  endsAt: string
}

const NOTHING_TYPED: DecisionFields = { reason: '', venueId: '', startsAt: '', endsAt: '' }
const SUGGESTION_HINT = 'Only when rejecting. In Singapore time.'

/** The decision for the backend; a field left empty is left out of it. */
function decisionFrom(outcome: BookingDecision['outcome'], typed: DecisionFields) {
  const decision: BookingDecision = { outcome }
  if (typed.reason !== '') {
    decision.reason = typed.reason
  }
  if (typed.venueId !== '') {
    decision.suggested_venue_id = Number(typed.venueId)
  }
  if (typed.startsAt !== '') {
    decision.suggested_starts_at = toBusinessTimeIso(typed.startsAt)
  }
  if (typed.endsAt !== '') {
    decision.suggested_ends_at = toBusinessTimeIso(typed.endsAt)
  }
  return decision
}

/**
 * Approves or rejects one waiting request (SCRUM-43 AC3). The reason is optional to approve and
 * required to reject, and an alternative venue, period or both may be suggested with a rejection
 * (SCRUM-70 AC1), all of which the backend decides: the fields are always here and their errors
 * come back from the backend rather than being checked twice.
 */
export function BookingDecisionForm({ requestId, purpose }: BookingDecisionFormProps) {
  const [typed, setTyped] = useState(NOTHING_TYPED)
  const decide = useDecideBookingRequest(requestId)
  const fieldErrors = fieldErrorsOf(decide.error)
  const hasFieldErrors = Object.keys(fieldErrors).length > 0

  function onChangeOf(field: keyof DecisionFields) {
    return (event: ChangeEvent<HTMLInputElement>) =>
      setTyped({ ...typed, [field]: event.target.value })
  }

  function send(outcome: BookingDecision['outcome']) {
    decide.mutate(decisionFrom(outcome, typed))
  }

  return (
    <div className="mt-4 space-y-3">
      <TextField
        label={`Reason for ${purpose}`}
        name="reason"
        autoComplete="off"
        value={typed.reason}
        onChange={onChangeOf('reason')}
        errors={fieldErrors.reason}
      />
      <fieldset className="space-y-3">
        <legend className="text-ink mb-1 text-sm font-medium">Suggest an alternative</legend>
        <TextField
          label={`Suggested venue ID for ${purpose}`}
          name="suggested_venue_id"
          type="number"
          min={1}
          hint="Optional."
          value={typed.venueId}
          onChange={onChangeOf('venueId')}
          errors={fieldErrors.suggested_venue_id}
        />
        <TextField
          label={`Suggested start for ${purpose}`}
          name="suggested_starts_at"
          type="datetime-local"
          hint={SUGGESTION_HINT}
          value={typed.startsAt}
          onChange={onChangeOf('startsAt')}
          errors={fieldErrors.suggested_starts_at}
        />
        <TextField
          label={`Suggested end for ${purpose}`}
          name="suggested_ends_at"
          type="datetime-local"
          hint={SUGGESTION_HINT}
          value={typed.endsAt}
          onChange={onChangeOf('endsAt')}
          errors={fieldErrors.suggested_ends_at}
        />
      </fieldset>
      {!hasFieldErrors && <ErrorAlert error={decide.error} />}
      <div className="flex gap-3">
        <Button
          isPending={decide.isPending}
          aria-label={`Approve ${purpose}`}
          onClick={() => send('approved')}
        >
          Approve
        </Button>
        <Button
          variant="secondary"
          isPending={decide.isPending}
          aria-label={`Reject ${purpose}`}
          onClick={() => send('rejected')}
        >
          Reject
        </Button>
      </div>
    </div>
  )
}
