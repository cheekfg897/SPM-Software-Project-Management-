import { PreparationForm } from '@/components/preparation/PreparationForm'

import type { EquipmentReservation } from '../api'
import { useUpdateReservationPreparation } from '../hooks'

interface ReservationPreparationFormProps {
  reference: string
  reservation: EquipmentReservation
}

/** Record one reservation's preparation status and notes (SCRUM-85 AC1, ADR-0081). */
export function ReservationPreparationForm({
  reference,
  reservation,
}: ReservationPreparationFormProps) {
  const prepare = useUpdateReservationPreparation(reference, reservation.id)
  return (
    <div className="min-w-56">
      <PreparationForm
        subject={reservation.equipment_type_name}
        current={reservation}
        mutation={prepare}
      />
    </div>
  )
}
