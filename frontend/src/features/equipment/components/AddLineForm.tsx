import { useId, useState } from 'react'
import type { FormEvent } from 'react'

import { Button } from '@/components/ui'

import type { EquipmentType } from '../api'
import { useAddEquipmentLine } from '../hooks'
import { changedFields, EMPTY_LINE_VALUES } from '../lineFormValues'

import { EquipmentLineFields } from './EquipmentLineFields'

interface AddLineFormProps {
  reference: string
  equipmentTypes: EquipmentType[]
}

/** Add one kind of equipment the event needs (SCRUM-37 AC1). The backend checks the values. */
export function AddLineForm({ reference, equipmentTypes }: AddLineFormProps) {
  const headingId = useId()
  const [values, setValues] = useState(EMPTY_LINE_VALUES)
  const add = useAddEquipmentLine(reference)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    add.mutate(changedFields(values, EMPTY_LINE_VALUES), {
      onSuccess: () => setValues(EMPTY_LINE_VALUES),
    })
  }

  return (
    <form
      aria-labelledby={headingId}
      onSubmit={handleSubmit}
      className="border-line/70 bg-surface/70 space-y-4 rounded-2xl border p-5"
    >
      <h3 id={headingId} className="font-display text-lg font-semibold tracking-tight">
        Add equipment
      </h3>
      <EquipmentLineFields
        equipmentTypes={equipmentTypes}
        values={values}
        onChange={setValues}
        error={add.error}
      />
      <Button type="submit" isPending={add.isPending}>
        Add line
      </Button>
    </form>
  )
}
