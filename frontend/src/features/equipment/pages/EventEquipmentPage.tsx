import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'

import { EquipmentContent } from '../components/EquipmentContent'

/**
 * Equipment for one event: what it needs (SCRUM-37), what is free for its period (SCRUM-45),
 * and what is held (SCRUM-46).
 */
export function EventEquipmentPage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { reference = '' } = useParams()

  return (
    <PageContainer
      title={`Equipment for ${reference}`}
      description="What this event needs, and what is free of each equipment type for its own start and end against that."
    >
      <div className="mt-8">
        <EquipmentContent reference={reference} />
      </div>
    </PageContainer>
  )
}
