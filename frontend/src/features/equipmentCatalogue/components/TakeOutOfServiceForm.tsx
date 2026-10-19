import { useId, useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, SelectField, TextField } from '@/components/ui'
import type { SelectOption } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { OutOfServiceBody, OutOfServiceReason } from '../api'
import { OUT_OF_SERVICE_REASON_LABELS } from '../constants'
import { useTakeOutOfService } from '../hooks'

const REASON_OPTIONS: SelectOption[] = Object.entries(OUT_OF_SERVICE_REASON_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** What the form holds: each field as entered, '' while blank. */
interface TakeOutValues {
  quantity: string
  reason: '' | OutOfServiceReason
}

const BLANK_VALUES: TakeOutValues = { quantity: '', reason: '' }

/** What sending the form sends. A blank field is left out, so the backend says what is missing. */
function takeOutBody(values: TakeOutValues): OutOfServiceBody {
  const body: OutOfServiceBody = {}
  if (values.quantity !== '') {
    body.quantity = Number(values.quantity)
  }
  if (values.reason !== '') {
    body.reason = values.reason
  }
  return body
}

/**
 * Take units of the type out of service as Damaged or Under Maintenance (SCRUM-47 AC1). How many
 * may go is the backend's to say: more than are in service is refused under the quantity.
 */
export function TakeOutOfServiceForm({ equipmentTypeId }: { equipmentTypeId: string }) {
  const headingId = useId()
  const [values, setValues] = useState(BLANK_VALUES)
  const takeOut = useTakeOutOfService(equipmentTypeId)
  const fieldErrors = fieldErrorsOf(takeOut.error)
  const hasFieldErrors = Object.keys(fieldErrors).length > 0

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    takeOut.mutate(takeOutBody(values), { onSuccess: () => setValues(BLANK_VALUES) })
  }

  return (
    <form
      aria-labelledby={headingId}
      onSubmit={handleSubmit}
      className="border-line/70 bg-surface/70 max-w-2xl space-y-4 rounded-2xl border p-5"
    >
      <h3 id={headingId} className="font-display text-lg font-semibold tracking-tight">
        Take units out of service
      </h3>
      {!hasFieldErrors && <ErrorAlert error={takeOut.error} />}
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="Quantity"
          name="quantity"
          type="number"
          inputMode="numeric"
          value={values.quantity}
          onChange={(event) => setValues({ ...values, quantity: event.target.value })}
          errors={fieldErrors.quantity}
        />
        <SelectField
          label="Reason"
          name="reason"
          options={REASON_OPTIONS}
          emptyLabel="Choose a reason"
          value={values.reason}
          // The options are the reasons' own values, so the choice is one of them or blank.
          onChange={(event) =>
            setValues({ ...values, reason: event.target.value as TakeOutValues['reason'] })
          }
          errors={fieldErrors.reason}
        />
      </div>
      <Button type="submit" isPending={takeOut.isPending}>
        Take out of service
      </Button>
    </form>
  )
}
