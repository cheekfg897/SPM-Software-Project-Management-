import { PageContainer } from '@/components/layout'

import { UnassignedQueue } from '../components/UnassignedQueue'

/** The Event Coordinator Lead's queue of event requests waiting for a coordinator (SCRUM-95). */
export function UnassignedQueuePage() {
  return (
    <PageContainer
      title="Unassigned requests"
      description="Give each new event request to an Event Coordinator by their email address."
    >
      <div className="mt-10">
        <UnassignedQueue />
      </div>
    </PageContainer>
  )
}
