import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'
import { ButtonLink } from '@/components/ui'
import { editEquipmentTypePath, ROUTES } from '@/config/routes'

import { EquipmentTypeDetails } from '../components/EquipmentTypeDetails'
import { EquipmentTypeLoader } from '../components/EquipmentTypeLoader'
import { OutOfServiceSection } from '../components/OutOfServiceSection'
import { useEquipmentType } from '../hooks'
import { useMayEditCatalogue } from '../useMayEditCatalogue'

/**
 * One equipment type's page, under its name (SCRUM-27 AC2). Technical Support can edit it (AC1,
 * AC3), and take its units out of service and back (SCRUM-47): the same people may do both.
 */
export function EquipmentTypePage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { equipmentTypeId = '' } = useParams()
  // The same query as the loader's below, so the name comes with it rather than separately.
  const type = useEquipmentType(equipmentTypeId)
  const mayEdit = useMayEditCatalogue()

  return (
    <PageContainer title={type.data?.name ?? 'Equipment type'}>
      <div className="mt-10 space-y-8">
        <EquipmentTypeLoader equipmentTypeId={equipmentTypeId}>
          {(loaded) => (
            <>
              <EquipmentTypeDetails type={loaded} />
              {mayEdit && (
                <>
                  <ButtonLink to={editEquipmentTypePath(loaded.id)} variant="secondary">
                    Edit
                  </ButtonLink>
                  <OutOfServiceSection type={loaded} />
                </>
              )}
            </>
          )}
        </EquipmentTypeLoader>
        <div>
          <ButtonLink to={ROUTES.EQUIPMENT_CATALOGUE} variant="ghost" className="px-0">
            All equipment
          </ButtonLink>
        </div>
      </div>
    </PageContainer>
  )
}
