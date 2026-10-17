import { PageContainer } from '@/components/layout'

import { NewEquipmentTypeForm } from '../components/NewEquipmentTypeForm'

/** Where Technical Support add an equipment type to the catalogue (SCRUM-27 AC1). */
export function NewEquipmentTypePage() {
  return (
    <PageContainer
      title="Add equipment type"
      description="Record a kind of equipment ConnectSphere holds, how many, and where they are kept."
    >
      <div className="mt-10">
        <NewEquipmentTypeForm />
      </div>
    </PageContainer>
  )
}
