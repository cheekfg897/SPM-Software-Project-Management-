import type { ReactNode } from 'react'

import type { ChangeRequest, Decision } from '../api'
import { describeAgainstNow } from '../changeRequest'
import type { ChangeableRecord } from '../changeRequest'
import { useDecideChangeRequest } from '../hooks'

import { ActionCard } from './ActionCard'
import { FactList } from './FactList'
import { OutcomeForm } from './OutcomeForm'
import { ReservedEquipment } from './ReservedEquipment'
import { VenueArrangementList } from './VenueArrangementList'

const EITHER_OUTCOME: readonly Decision['outcome'][] = ['approved', 'rejected']

interface DecideChangeRequestProps {
  record: ChangeableRecord
  changeRequest: ChangeRequest
}

function ReviewHeading({ children }: { children: ReactNode }) {
  return <h4 className="text-ink-muted text-sm font-medium">{children}</h4>
}

/**
 * The coordinator's review of a Pending change request (SCRUM-57): each change beside what the
 * event holds now, every venue booking and the equipment reserved for it (AC1); then approve or
 * reject it, a rejection with a reason (AC2, AC3). Whether the decision is allowed is the
 * backend's call, and its refusal shows as it comes (AC5, AC8).
 */
export function DecideChangeRequest({ record, changeRequest }: DecideChangeRequestProps) {
  const decide = useDecideChangeRequest(record.reference, changeRequest.id)
  const facts = changeRequest.changes.map((change) => describeAgainstNow(change, record))
  return (
    <ActionCard
      title="Decide the change request"
      description="Approving changes the event. The organiser is told of your decision and its reason."
    >
      <FactList facts={facts} />
      <ReviewHeading>Venue bookings</ReviewHeading>
      <VenueArrangementList arrangements={record.venue_arrangements ?? []} />
      <ReviewHeading>Equipment reserved</ReviewHeading>
      <ReservedEquipment reference={record.reference} />
      <OutcomeForm outcomes={EITHER_OUTCOME} mutation={decide} />
    </ActionCard>
  )
}
