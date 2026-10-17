import { useId, useState } from 'react'
import type { FormEvent } from 'react'

import { Button } from '@/components/ui'

import type { EquipmentLine, EquipmentType } from '../api'
import { equipmentTypeName } from '../equipmentTypeName'
import { useUpdateEquipmentLine } from '../hooks'
import { changedFields, valuesOfLine } from '../lineFormValues'

import { EquipmentLineFields } from './EquipmentLineFields'

interface ChangeLineFormProps {
  reference: string
  equipmentTypes: EquipmentType[]
  line: EquipmentLine
  /** Close the form: after a saved change, or on cancel. */
  onDone: () => void
}

/** Change one of the event's equipment lines (SCRUM-37 AC2), sending only what changed. */
export function ChangeLineForm({ reference, equipmentTypes, line, onDone }: ChangeLineFormProps) {
  const headingId = useId()
  const original = valuesOfLine(line)
  const [values, setValues] = useState(original)
  const update = useUpdateEquipmentLine(reference)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    update.mutate({ lineId: line.id, body: changedFields(values, original) }, { onSuccess: onDone })
  }

  return (
    <form
      aria-labelledby={headingId}
      onSubmit={handleSubmit}
      className="border-line/70 bg-surface/70 space-y-4 rounded-2xl border p-5"
    >
      <h3 id={headingId} className="font-display text-lg font-semibold tracking-tight">
        Change {equipmentTypeName(equipmentTypes, line.equipment_type_id)}
      </h3>
      <EquipmentLineFields
        equipmentTypes={equipmentTypes}
        values={values}
        onChange={setValues}
        error={update.error}
      />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" isPending={update.isPending}>
          Save changes
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
