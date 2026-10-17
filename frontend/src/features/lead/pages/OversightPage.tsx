import { PageContainer } from '@/components/layout'

import { ActiveEventList } from '../components/ActiveEventList'
import { CoordinatorWorkloads } from '../components/CoordinatorWorkloads'
import { LeadNav } from '../components/LeadNav'
import { OversightSection } from '../components/OversightSection'

/**
 * The Event Coordinator Lead's view of who is working on what (SCRUM-96, SCRUM-24 AC3): each
 * coordinator's workload first, to help choose who takes an event, then every active event.
 */
export function OversightPage() {
  return (
    <PageContainer
      title="Coordinator oversight"
      description="Who is working on what. Move an event to another Event Coordinator by their email address."
    >
      <LeadNav />
      <OversightSection
        title="Workload"
        description="Each Event Coordinator and the active events they hold."
      >
        <CoordinatorWorkloads />
      </OversightSection>
      <OversightSection
        title="Active events"
        description="Every event still being worked on, newest first."
      >
        <ActiveEventList />
      </OversightSection>
    </PageContainer>
  )
}
