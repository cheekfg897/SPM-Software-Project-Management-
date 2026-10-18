import { PageContainer } from '@/components/layout'

import { PendingDecisionQueue } from '../components/PendingDecisionQueue'

/** Venue Staff's queue of booking requests waiting for a decision or a hold (SCRUM-43, SCRUM-75). */
export function BookingDecisionsPage() {
  return (
    <PageContainer
      title="Venue booking requests"
      description="Approve a request to book the venue, hold it until an expiry while its event's venues are finalised, or reject it with a reason. The coordinator is told each time."
    >
      <div className="mt-10">
        <PendingDecisionQueue />
      </div>
    </PageContainer>
  )
}
