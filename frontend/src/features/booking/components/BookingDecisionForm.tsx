import { useState } from 'react'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import { useDecideBookingRequest } from '../hooks'

interface BookingDecisionFormProps {
  requestId: number
  /** The request's purpose, so each field and button says which request it belongs to. */
  purpose: string
}

/**
 * Approves or rejects one waiting request (SCRUM-43 AC3). The reason is optional to
 * approve and required to reject, which the backend decides: the field is always here
 * and its error comes back from the backend rather than being checked twice.
 */
export function BookingDecisionForm({ requestId, purpose }: BookingDecisionFormProps) {
  const [reason, setReason] = useState('')
  const decide = useDecideBookingRequest(requestId)
  const reasonErrors = fieldErrorsOf(decide.error).reason

  function send(outcome: 'approved' | 'rejected') {
    decide.mutate(reason === '' ? { outcome } : { outcome, reason })
  }

  return (
    <div className="mt-4 space-y-3">
      <TextField
        label={`Reason for ${purpose}`}
        name="reason"
        autoComplete="off"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        errors={reasonErrors}
      />
      {reasonErrors === undefined && <ErrorAlert error={decide.error} />}
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
