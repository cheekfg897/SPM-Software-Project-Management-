import { useState } from 'react'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import type { ButtonVariant } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { Decision, DecisionChoice } from '../api'
import { useDecideEventRequest } from '../hooks'

import { ActionCard } from './ActionCard'

interface OutcomeButton {
  label: string
  variant: ButtonVariant
}

const OUTCOME_BUTTON: Record<Decision['outcome'], OutcomeButton> = {
  approved: { label: 'Approve', variant: 'primary' },
  rejected: { label: 'Reject', variant: 'secondary' },
}

interface DecisionFormProps {
  reference: string
  /** The outcomes that can apply to the request now, in the order their buttons show. */
  outcomes: readonly Decision['outcome'][]
}

/**
 * Approve or reject a request, or change its decision (SCRUM-31 AC4, AC6). The reason is sent
 * only when one is typed; whether one is needed is the backend's rule, and its message shows
 * under the box (ADR-0049).
 */
export function DecisionForm({ reference, outcomes }: DecisionFormProps) {
  const [reason, setReason] = useState('')
  const decide = useDecideEventRequest(reference)

  function send(outcome: Decision['outcome']) {
    const choice: DecisionChoice = reason === '' ? { outcome } : { outcome, reason }
    decide.mutate(choice, { onSuccess: () => setReason('') })
  }

  return (
    <ActionCard title="Decide" description="The organiser is told of your decision and its reason.">
      <ErrorAlert error={decide.error} />
      <TextAreaField
        label="Reason"
        name="reason"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        errors={fieldErrorsOf(decide.error).reason}
      />
      <div className="flex flex-wrap gap-3">
        {outcomes.map((outcome) => (
          <Button
            key={outcome}
            variant={OUTCOME_BUTTON[outcome].variant}
            isPending={decide.isPending}
            onClick={() => send(outcome)}
          >
            {OUTCOME_BUTTON[outcome].label}
          </Button>
        ))}
      </div>
    </ActionCard>
  )
}
