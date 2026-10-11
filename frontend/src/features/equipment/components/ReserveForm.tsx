import { useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { EquipmentAvailability } from '../api'
import { useReserveEquipment } from '../hooks'

interface ReserveFormProps {
  reference: string
  equipmentType: EquipmentAvailability
}

/** Reserve units of one equipment type for the event. The backend decides how many may be. */
export function ReserveForm({ reference, equipmentType }: ReserveFormProps) {
  const [quantity, setQuantity] = useState('')
  const reserve = useReserveEquipment(reference)
  const fieldErrors = fieldErrorsOf(reserve.error)
  const hasFieldErrors = Object.keys(fieldErrors).length > 0

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    reserve.mutate(
      { equipment_type_id: equipmentType.equipment_type_id, quantity: Number(quantity) },
      { onSuccess: () => setQuantity('') },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="flex min-w-48 flex-col gap-3">
      {!hasFieldErrors && <ErrorAlert error={reserve.error} />}
      <TextField
        label={`Quantity of ${equipmentType.equipment_type_name}`}
        name="quantity"
        type="number"
        inputMode="numeric"
        value={quantity}
        onChange={(event) => setQuantity(event.target.value)}
        errors={[...(fieldErrors.quantity ?? []), ...(fieldErrors.equipment_type_id ?? [])]}
      />
      <Button
        type="submit"
        isPending={reserve.isPending}
        aria-label={`Reserve ${equipmentType.equipment_type_name}`}
      >
        Reserve
      </Button>
    </form>
  )
}
