import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'

import { EditEquipmentTypeForm } from '../components/EditEquipmentTypeForm'
import { EquipmentTypeLoader } from '../components/EquipmentTypeLoader'

/** Where Technical Support change an equipment type (SCRUM-27 AC1). */
export function EditEquipmentTypePage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { equipmentTypeId = '' } = useParams()

  return (
    <PageContainer
      title="Edit equipment type"
      description="Change what the catalogue records. Availability is worked out from these numbers."
    >
      <div className="mt-10">
        <EquipmentTypeLoader equipmentTypeId={equipmentTypeId}>
          {(type) => <EditEquipmentTypeForm type={type} />}
        </EquipmentTypeLoader>
      </div>
    </PageContainer>
  )
}
