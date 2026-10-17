import { PageContainer } from '@/components/layout'
import { ButtonLink, EmptyState, ErrorAlert } from '@/components/ui'
import { ROUTES } from '@/config/routes'

import { EquipmentTypeTable } from '../components/EquipmentTypeTable'
import { LoadingStatus } from '../components/LoadingStatus'
import { useEquipmentTypes } from '../hooks'
import { useMayEditCatalogue } from '../useMayEditCatalogue'

/** The catalogue as the backend lists it, or why it can't be shown. */
function CatalogueContent() {
  const types = useEquipmentTypes()

  if (types.isPending) {
    return <LoadingStatus what="the equipment catalogue" />
  }
  if (types.isError) {
    return <ErrorAlert error={types.error} />
  }
  // The backend sends no message for an empty catalogue, so this wording is ours (ADR-0054).
  if (types.data.length === 0) {
    return <EmptyState message="No equipment types yet." />
  }
  return <EquipmentTypeTable types={types.data} />
}

/**
 * Every equipment type ConnectSphere holds, with how many of each (SCRUM-27 AC2). Every member of
 * staff reads it; Technical Support also get the link to add a type (AC3).
 */
export function EquipmentCataloguePage() {
  const mayEdit = useMayEditCatalogue()

  return (
    <PageContainer
      title="Equipment catalogue"
      description="Every equipment type ConnectSphere holds, how many of each, and where they are kept."
    >
      {mayEdit && (
        <div className="mt-6">
          <ButtonLink to={ROUTES.NEW_EQUIPMENT_TYPE}>Add equipment type</ButtonLink>
        </div>
      )}
      <div className="mt-10">
        <CatalogueContent />
      </div>
    </PageContainer>
  )
}
