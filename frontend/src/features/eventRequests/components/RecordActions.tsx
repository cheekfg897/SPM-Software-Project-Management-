import { Button, ErrorAlert, RefusalAlert } from '@/components/ui'
import type { EventRequestStatus } from '@/config/eventStatus'

import type { EventRecord } from '../api'
import { useCompleteEvent, useConfirmEvent, useSendToSafetyReview } from '../hooks'

import { ActionCard } from './ActionCard'
import { RecordSection } from './RecordSection'
import { RegistrationSettingsForm } from './RegistrationSettingsForm'
import { RejectEventForm } from './RejectEventForm'

/** Ask the Safety Officer to check an approved event; a refusal names every gap (SCRUM-97). */
function SendToSafetyReview({ record }: { record: EventRecord }) {
  const send = useSendToSafetyReview(record.reference)
  return (
    <ActionCard
      title="Send to safety review"
      description="The Safety Officer is asked to check the event. Every venue arrangement must be approved and every equipment request answered first."
    >
      <RefusalAlert error={send.error} />
      <Button isPending={send.isPending} onClick={() => send.mutate()}>
        Send to safety review
      </Button>
    </ActionCard>
  )
}

/**
 * Confirm an event in safety review; a refusal names every approval still missing (SCRUM-49).
 * The organiser is told by the backend's own notification.
 */
function ConfirmEvent({ record }: { record: EventRecord }) {
  const confirm = useConfirmEvent(record.reference)
  return (
    <ActionCard
      title="Confirm the event"
      description="Once the Safety Officer has approved it and every venue and equipment request is settled. The organiser is told."
    >
      <RefusalAlert error={confirm.error} />
      <Button isPending={confirm.isPending} onClick={() => confirm.mutate()}>
        Confirm event
      </Button>
    </ActionCard>
  )
}

/** Mark a confirmed event completed; the backend says when it hasn't ended yet (SCRUM-68). */
function MarkCompleted({ record }: { record: EventRecord }) {
  const complete = useCompleteEvent(record.reference)
  return (
    <ActionCard
      title="Mark completed"
      description="Once the event has ended. A completed event can no longer be changed."
    >
      <ErrorAlert error={complete.error} />
      <Button isPending={complete.isPending} onClick={() => complete.mutate()}>
        Mark completed
      </Button>
    </ActionCard>
  )
}

/** Every planning action's card, each drawn for the event it acts on. */
const ACTION_CARDS = {
  sendToSafetyReview: SendToSafetyReview,
  confirm: ConfirmEvent,
  registration: RegistrationSettingsForm,
  complete: MarkCompleted,
  reject: RejectEventForm,
}

type PlanningAction = keyof typeof ACTION_CARDS

const NOTHING_TO_OFFER: readonly PlanningAction[] = []

/**
 * The planning actions offered in each status, in the order they show: only the status the
 * backend accepts each one in (ADR-0075). Whether it goes ahead there is still the backend's
 * call, and its refusal is shown.
 */
const PLANNING_ACTIONS_BY_STATUS: Record<EventRequestStatus, readonly PlanningAction[]> = {
  draft: NOTHING_TO_OFFER,
  submitted: NOTHING_TO_OFFER,
  under_review: NOTHING_TO_OFFER,
  awaiting_clarification: NOTHING_TO_OFFER,
  approved: ['sendToSafetyReview', 'reject'],
  safety_review: ['confirm', 'reject'],
  confirmed: ['registration', 'complete'],
  completed: NOTHING_TO_OFFER,
  cancelled: NOTHING_TO_OFFER,
  rejected: NOTHING_TO_OFFER,
}

/**
 * The assigned coordinator's planning actions on an event once it is approved: send it to
 * safety review (SCRUM-97), confirm it (SCRUM-49), set its registration (SCRUM-69), mark it
 * completed (SCRUM-68) (ADR-0075), and reject it while it is in planning (SCRUM-49 AC9,
 * ADR-0093). Nothing is drawn when no action can apply.
 */
export function RecordActions({ record }: { record: EventRecord }) {
  const actions = PLANNING_ACTIONS_BY_STATUS[record.status]
  if (actions.length === 0) {
    return null
  }
  return (
    <RecordSection title="Planning">
      <div className="space-y-4">
        {actions.map((action) => {
          const Card = ACTION_CARDS[action]
          return <Card key={action} record={record} />
        })}
      </div>
    </RecordSection>
  )
}
