import { useState } from 'react'
import type { UseMutationResult } from '@tanstack/react-query'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import type { ButtonVariant } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { Decision, DecisionChoice } from '../api'

interface OutcomeButton {
  label: string
  variant: ButtonVariant
}

const OUTCOME_BUTTON: Record<Decision['outcome'], OutcomeButton> = {
  approved: { label: 'Approve', variant: 'primary' },
  rejected: { label: 'Reject', variant: 'secondary' },
}

interface OutcomeFormProps {
  /** The outcomes that can apply now, in the order their buttons show. */
  outcomes: readonly Decision['outcome'][]
  /** Sends the outcome chosen, with the reason when one is typed. */
  mutation: UseMutationResult<unknown, Error, DecisionChoice>
}

/**
 * A reason box and a button for each outcome: the coordinator's decision on an event request
 * (SCRUM-31) or on a change request (SCRUM-57). The reason is sent only when one is typed;
 * whether one is needed is the backend's rule, and its message shows under the box (ADR-0060).
 */
export function OutcomeForm({ outcomes, mutation }: OutcomeFormProps) {
  const [reason, setReason] = useState('')

  function send(outcome: Decision['outcome']) {
    const choice: DecisionChoice = reason === '' ? { outcome } : { outcome, reason }
    mutation.mutate(choice, { onSuccess: () => setReason('') })
  }

  return (
    <>
      <ErrorAlert error={mutation.error} />
      <TextAreaField
        label="Reason"
        name="reason"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        errors={fieldErrorsOf(mutation.error).reason}
      />
      <div className="flex flex-wrap gap-3">
        {outcomes.map((outcome) => (
          <Button
            key={outcome}
            variant={OUTCOME_BUTTON[outcome].variant}
            isPending={mutation.isPending}
            onClick={() => send(outcome)}
          >
            {OUTCOME_BUTTON[outcome].label}
          </Button>
        ))}
      </div>
    </>
  )
}
