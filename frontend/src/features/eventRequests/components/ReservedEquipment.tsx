import { EmptyState, ErrorAlert, Spinner } from '@/components/ui'
import { useEventReservations } from '@/features/equipment/hooks'

const NOTHING_RESERVED = 'No equipment is reserved for this event.'

/**
 * The equipment reserved for the event, e.g. "2 × Projector", read from the equipment module's
 * own route, as the coordinator's record carries no reservations (SCRUM-57 AC1, ADR-0127).
 */
export function ReservedEquipment({ reference }: { reference: string }) {
  const reservations = useEventReservations(reference)
  if (reservations.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-2">
        <Spinner /> Loading the reserved equipment…
      </p>
    )
  }
  if (reservations.isError) {
    return <ErrorAlert error={reservations.error} />
  }
  if (reservations.data.length === 0) {
    return <EmptyState message={NOTHING_RESERVED} />
  }
  return (
    <ul className="text-ink list-disc space-y-1 pl-5 text-sm">
      {reservations.data.map((reservation) => (
        <li key={reservation.id}>
          {`${String(reservation.quantity)} × ${reservation.equipment_type_name}`}
        </li>
      ))}
    </ul>
  )
}
