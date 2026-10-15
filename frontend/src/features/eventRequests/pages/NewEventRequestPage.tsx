import { PageContainer } from '@/components/layout'

import { NewEventRequestForm } from '../components/NewEventRequestForm'

/** Where an Event Organiser describes a new event for ConnectSphere to plan (SCRUM-19). */
export function NewEventRequestPage() {
  return (
    <PageContainer
      title="New event request"
      description="Tell us about your event. Your coordinator plans it from what you write here."
    >
      <div className="mt-10">
        <NewEventRequestForm />
      </div>
    </PageContainer>
  )
}
