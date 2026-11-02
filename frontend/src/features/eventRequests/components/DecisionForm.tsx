import type { Decision } from '../api'
import { useDecideEventRequest } from '../hooks'

import { ActionCard } from './ActionCard'
import { OutcomeForm } from './OutcomeForm'

interface DecisionFormProps {
  reference: string
  /** The outcomes that can apply to the request now, in the order their buttons show. */
  outcomes: readonly Decision['outcome'][]
}

/** Approve or reject a request, or change its decision (SCRUM-31 AC4, AC6). */
export function DecisionForm({ reference, outcomes }: DecisionFormProps) {
  const decide = useDecideEventRequest(reference)
  return (
    <ActionCard title="Decide" description="The organiser is told of your decision and its reason.">
      <OutcomeForm outcomes={outcomes} mutation={decide} />
    </ActionCard>
  )
}
