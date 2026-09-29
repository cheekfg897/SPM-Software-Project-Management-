import { PageContainer } from '@/components/layout'

import { Greeting } from '../components/Greeting'

/** The landing view for every staff role (SCRUM-6 AC3). Their work lists come here later. */
export function StaffHomePage() {
  return (
    <PageContainer
      title="Staff home"
      description="The events and requests you look after will appear here."
    >
      <Greeting />
    </PageContainer>
  )
}
