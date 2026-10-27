import { ErrorAlert, Spinner } from '@/components/ui'
import { useEquipmentTypes } from '@/features/equipmentCatalogue/hooks'

import {
  useEventAvailability,
  useEventEquipmentLines,
  useEventReassessments,
  useEventReservations,
} from '../hooks'

import { AvailabilityTable } from './AvailabilityTable'
import { EquipmentNeeds } from './EquipmentNeeds'
import { ReassessmentList } from './ReassessmentList'
import { ReservationList } from './ReservationList'

interface EquipmentContentProps {
  reference: string
}

/**
 * What the event needs, what a change left to reassess (SCRUM-60), the availability table and the
 * reservation list, or the loading or error state in their place. The first failure's message is
 * shown: they share the event, so one "Event request not found." is enough.
 */
export function EquipmentContent({ reference }: EquipmentContentProps) {
  const needs = useEventEquipmentLines(reference)
  const equipmentTypes = useEquipmentTypes()
  const availability = useEventAvailability(reference)
  const reservations = useEventReservations(reference)
  const reassessments = useEventReassessments(reference)

  const queries = [needs, equipmentTypes, availability, reservations, reassessments]
  const failed = queries.find((query) => query.isError)
  if (failed !== undefined) {
    return <ErrorAlert error={failed.error} />
  }
  // Until all five have answered. Checking `data` rather than `isPending` lets TypeScript see
  // each one is there below.
  if (
    needs.data === undefined ||
    equipmentTypes.data === undefined ||
    availability.data === undefined ||
    reservations.data === undefined ||
    reassessments.data === undefined
  ) {
    return (
      <p className="text-ink-muted flex items-center gap-2">
        <Spinner /> Loading equipment…
      </p>
    )
  }
  return (
    <div className="space-y-10">
      <EquipmentNeeds
        reference={reference}
        needs={needs.data}
        equipmentTypes={equipmentTypes.data}
      />
      <ReassessmentList reference={reference} reassessments={reassessments.data} />
      <section aria-labelledby="availability-heading" className="space-y-4">
        <h2 id="availability-heading" className="text-xl font-semibold">
          Availability
        </h2>
        <AvailabilityTable reference={reference} rows={availability.data} />
      </section>
      <section aria-labelledby="reservations-heading" className="space-y-4">
        <h2 id="reservations-heading" className="text-xl font-semibold">
          Reserved for this event
        </h2>
        <ReservationList reference={reference} reservations={reservations.data} />
      </section>
    </div>
  )
}
