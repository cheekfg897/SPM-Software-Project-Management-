import { PageContainer } from '@/components/layout'

import { PendingDecisionQueue } from '../components/PendingDecisionQueue'

/** Venue Staff's queue of booking requests waiting for a decision (SCRUM-43). */
export function BookingDecisionsPage() {
  return (
    <PageContainer
      title="Venue booking requests"
      description="Approve a request to book the venue, or reject it with a reason. The coordinator who raised it is told either way."
    >
      <div className="mt-10">
        <PendingDecisionQueue />
      </div>
    </PageContainer>
  )
}
