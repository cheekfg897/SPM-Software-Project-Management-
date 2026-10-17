import { TextAreaField, TextField } from '@/components/ui'
import type { FieldErrors } from '@/lib/api'

import type { EquipmentType } from '../api'

interface EquipmentTypeFieldsProps {
  /** The backend's messages, by field. */
  fieldErrors: FieldErrors
  /** The type being edited; left out when adding one. */
  initial?: EquipmentType
}

/**
 * The fields of an equipment type, named as the API names them (SCRUM-27 AC1). The place is a
 * venue's number or a store's name: the backend says if neither or both are filled in, under the
 * venue number, where it reports every problem with the place (ADR-0014).
 */
export function EquipmentTypeFields({ fieldErrors, initial }: EquipmentTypeFieldsProps) {
  return (
    <div className="space-y-6">
      <TextField label="Name" name="name" defaultValue={initial?.name} errors={fieldErrors.name} />
      <TextAreaField
        label="Description"
        name="description"
        hint="Optional. What it is, and anything worth knowing before it is reserved."
        defaultValue={initial?.description ?? ''}
        errors={fieldErrors.description}
      />
      <TextField
        label="Total quantity held"
        name="total_quantity"
        type="number"
        inputMode="numeric"
        defaultValue={initial?.total_quantity}
        errors={fieldErrors.total_quantity}
      />
      <fieldset className="space-y-4">
        <legend className="font-display text-lg font-semibold tracking-tight">
          Where it is kept
        </legend>
        <p className="text-ink-muted text-sm">
          Fill in one: the venue's number, or the store's name.
        </p>
        <TextField
          label="Venue number"
          name="venue_id"
          type="number"
          inputMode="numeric"
          defaultValue={initial?.venue_id ?? ''}
          errors={fieldErrors.venue_id}
        />
        <TextField
          label="Store name"
          name="store_name"
          defaultValue={initial?.store_name ?? ''}
          errors={fieldErrors.store_name}
        />
      </fieldset>
    </div>
  )
}
