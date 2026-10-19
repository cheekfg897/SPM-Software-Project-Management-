import { ErrorAlert } from '@/components/ui'

import type { EquipmentType } from '../api'
import { useOutOfService } from '../hooks'

import { LoadingStatus } from './LoadingStatus'
import { OutOfServiceList } from './OutOfServiceList'
import { TakeOutOfServiceForm } from './TakeOutOfServiceForm'

/** The type's units out of service, once the backend has listed them. */
function OutOfServiceContent({ type }: { type: EquipmentType }) {
  const entries = useOutOfService(String(type.id))

  if (entries.isPending) {
    return <LoadingStatus what="units out of service" />
  }
  if (entries.isError) {
    return <ErrorAlert error={entries.error} />
  }
  return <OutOfServiceList type={type} entries={entries.data} />
}

/**
 * Technical Support's view of the type's units out of service, and the form to take more out
 * (SCRUM-47 AC1, AC2, AC4). Only Technical Support may read or change them.
 */
export function OutOfServiceSection({ type }: { type: EquipmentType }) {
  return (
    <section aria-labelledby="out-of-service-heading" className="space-y-4">
      <h2 id="out-of-service-heading" className="text-xl font-semibold">
        Out of service
      </h2>
      <p className="text-ink-muted max-w-2xl">
        Damaged units and units under maintenance are not available to any event until they are back
        in service.
      </p>
      <OutOfServiceContent type={type} />
      <TakeOutOfServiceForm equipmentTypeId={String(type.id)} />
    </section>
  )
}
