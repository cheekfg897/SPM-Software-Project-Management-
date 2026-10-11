import { ErrorAlert, Spinner } from '@/components/ui'

import { useEventAvailability, useEventReservations } from '../hooks'

import { AvailabilityTable } from './AvailabilityTable'
import { ReservationList } from './ReservationList'

interface EquipmentContentProps {
  reference: string
}

/** The availability table and the reservation list, or the loading or error state in their place. */
export function EquipmentContent({ reference }: EquipmentContentProps) {
  const availability = useEventAvailability(reference)
  const reservations = useEventReservations(reference)

  if (availability.isError) {
    return <ErrorAlert error={availability.error} />
  }
  if (reservations.isError) {
    return <ErrorAlert error={reservations.error} />
  }
  if (availability.isPending || reservations.isPending) {
    return (
      <p className="text-ink-muted flex items-center gap-2">
        <Spinner /> Loading equipment…
      </p>
    )
  }
  return (
    <div className="space-y-10">
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
        <ReservationList reservations={reservations.data} />
      </section>
    </div>
  )
}
