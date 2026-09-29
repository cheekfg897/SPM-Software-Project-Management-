import { PageContainer } from '@/components/layout'

import { Greeting } from '../components/Greeting'

/** The Event Organiser's landing view (SCRUM-6 AC3). Their event requests come here later. */
export function OrganiserHomePage() {
  return (
    <PageContainer title="Your events" description="Your event requests will appear here.">
      <Greeting />
    </PageContainer>
  )
}
