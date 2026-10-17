import { Button, ErrorAlert } from '@/components/ui'
import type { EventRequestStatus } from '@/config/eventStatus'

import type { Decision, EventRequest } from '../api'
import { useRequestClarification, useStartReview } from '../hooks'

import { ActionCard } from './ActionCard'
import { DecisionForm } from './DecisionForm'
import { MessageForm } from './MessageForm'
import { RecordSection } from './RecordSection'

/** What the coordinator may be offered for a request in one status. */
interface ReviewOptions {
  canStartReview: boolean
  outcomes: readonly Decision['outcome'][]
  canAskForClarification: boolean
}

const NOTHING_TO_OFFER: ReviewOptions = {
  canStartReview: false,
  outcomes: [],
  canAskForClarification: false,
}
const EITHER_OUTCOME: readonly Decision['outcome'][] = ['approved', 'rejected']

/**
 * The actions that can apply in each status (ADR-0060). Only buttons that can't apply are
 * hidden: the backend still decides each action, and its refusal is shown. A question can be
 * asked only under review (SCRUM-32 AC1); a request awaiting its answer can be rejected but not
 * approved (SCRUM-32 AC3), and a decided one can be decided again (SCRUM-31 AC6).
 */
const REVIEW_OPTIONS_BY_STATUS: Record<EventRequestStatus, ReviewOptions> = {
  draft: NOTHING_TO_OFFER,
  submitted: { canStartReview: true, outcomes: EITHER_OUTCOME, canAskForClarification: false },
  under_review: { canStartReview: false, outcomes: EITHER_OUTCOME, canAskForClarification: true },
  awaiting_clarification: {
    canStartReview: false,
    outcomes: ['rejected'],
    canAskForClarification: false,
  },
  approved: { canStartReview: false, outcomes: EITHER_OUTCOME, canAskForClarification: false },
  rejected: { canStartReview: false, outcomes: EITHER_OUTCOME, canAskForClarification: false },
  safety_review: NOTHING_TO_OFFER,
  confirmed: NOTHING_TO_OFFER,
  completed: NOTHING_TO_OFFER,
  cancelled: NOTHING_TO_OFFER,
}

function StartReview({ reference }: { reference: string }) {
  const start = useStartReview(reference)
  return (
    <ActionCard
      title="Start the review"
      description="Moves the request to Under review, so the organiser can see you're on it."
    >
      <ErrorAlert error={start.error} />
      <Button isPending={start.isPending} onClick={() => start.mutate()}>
        Start review
      </Button>
    </ActionCard>
  )
}

function AskForClarification({ reference }: { reference: string }) {
  const ask = useRequestClarification(reference)
  return (
    <ActionCard
      title="Ask the organiser"
      description="The organiser is told of your question, and the request waits for their answer."
    >
      <MessageForm
        label="Question"
        field="message"
        submitLabel="Ask for clarification"
        mutation={ask}
      />
    </ActionCard>
  )
}

/**
 * The assigned coordinator's review of a request: start it, decide it, change the decision, or
 * ask the organiser a question (SCRUM-31 AC3, AC4, AC6; SCRUM-32 AC1). Nothing is drawn when no
 * action can apply.
 */
export function ReviewActions({ request }: { request: EventRequest }) {
  const { canStartReview, outcomes, canAskForClarification } =
    REVIEW_OPTIONS_BY_STATUS[request.status]
  if (!canStartReview && outcomes.length === 0 && !canAskForClarification) {
    return null
  }
  return (
    <RecordSection title="Review">
      <div className="space-y-4">
        {canStartReview && <StartReview reference={request.reference} />}
        {outcomes.length > 0 && <DecisionForm reference={request.reference} outcomes={outcomes} />}
        {canAskForClarification && <AskForClarification reference={request.reference} />}
      </div>
    </RecordSection>
  )
}
