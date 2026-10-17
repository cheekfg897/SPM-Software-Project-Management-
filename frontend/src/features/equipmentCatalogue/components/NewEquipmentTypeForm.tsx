import type { FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { Button, ButtonLink, ErrorAlert } from '@/components/ui'
import { equipmentTypePath, ROUTES } from '@/config/routes'
import { fieldErrorsOf } from '@/lib/api'

import { inputFromForm } from '../equipmentTypeForm'
import { useCreateEquipmentType } from '../hooks'

import { EquipmentTypeFields } from './EquipmentTypeFields'

/**
 * A new equipment type (SCRUM-27 AC1). Once the backend saves it, its page opens; a refusal keeps
 * what was typed and shows the backend's messages.
 */
export function NewEquipmentTypeForm() {
  const create = useCreateEquipmentType()
  const navigate = useNavigate()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    create.mutate(inputFromForm(new FormData(event.currentTarget)), {
      onSuccess: (saved) => void navigate(equipmentTypePath(saved.id)),
    })
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-8">
      <ErrorAlert error={create.error} />
      <EquipmentTypeFields fieldErrors={fieldErrorsOf(create.error)} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" isPending={create.isPending}>
          Add equipment type
        </Button>
        <ButtonLink to={ROUTES.EQUIPMENT_CATALOGUE} variant="ghost">
          Cancel
        </ButtonLink>
      </div>
    </form>
  )
}
