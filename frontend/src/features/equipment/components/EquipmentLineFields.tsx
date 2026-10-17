import { ErrorAlert, Field, TextAreaField, TextField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { EquipmentType } from '../api'
import type { LineFormValues } from '../lineFormValues'

interface EquipmentLineFieldsProps {
  equipmentTypes: EquipmentType[]
  values: LineFormValues
  onChange: (values: LineFormValues) => void
  /** The last refusal: its field messages go under the fields, anything else in an alert. */
  error: Error | null
}

/** An equipment line's type, quantity and technical notes, with the backend's messages. */
export function EquipmentLineFields({
  equipmentTypes,
  values,
  onChange,
  error,
}: EquipmentLineFieldsProps) {
  const fieldErrors = fieldErrorsOf(error)
  const hasFieldErrors = Object.keys(fieldErrors).length > 0

  return (
    <>
      {!hasFieldErrors && <ErrorAlert error={error} />}
      <Field label="Equipment type" errors={fieldErrors.equipment_type_id}>
        {(control) => (
          <select
            {...control}
            name="equipment_type_id"
            value={values.equipment_type_id}
            onChange={(event) => onChange({ ...values, equipment_type_id: event.target.value })}
            className="border-line bg-surface text-ink focus:border-flare/70 aria-invalid:border-danger w-full rounded-xl border px-4 py-2.5 focus:outline-none"
          >
            <option value="">Choose equipment</option>
            {equipmentTypes.map((equipmentType) => (
              <option key={equipmentType.id} value={String(equipmentType.id)}>
                {equipmentType.name}
              </option>
            ))}
          </select>
        )}
      </Field>
      <TextField
        label="Quantity"
        name="quantity"
        type="number"
        inputMode="numeric"
        value={values.quantity}
        onChange={(event) => onChange({ ...values, quantity: event.target.value })}
        errors={fieldErrors.quantity}
      />
      <TextAreaField
        label="Technical notes"
        name="notes"
        hint="For Technical Support: the model, connections or where it goes."
        value={values.notes}
        onChange={(event) => onChange({ ...values, notes: event.target.value })}
        errors={fieldErrors.notes}
      />
    </>
  )
}
