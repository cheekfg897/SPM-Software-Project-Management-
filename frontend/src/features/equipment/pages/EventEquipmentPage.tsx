import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'

import { EquipmentContent } from '../components/EquipmentContent'

/** Equipment for one event (SCRUM-45, SCRUM-46): what is free for its period, and what is held. */
export function EventEquipmentPage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { reference = '' } = useParams()

  return (
    <PageContainer
      title={`Equipment for ${reference}`}
      description="What is free of each equipment type for this event's own start and end, against what it asks for."
    >
      <div className="mt-8">
        <EquipmentContent reference={reference} />
      </div>
    </PageContainer>
  )
}
