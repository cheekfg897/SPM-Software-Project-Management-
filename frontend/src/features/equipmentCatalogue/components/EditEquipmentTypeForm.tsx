import type { FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { Button, ButtonLink, ErrorAlert } from '@/components/ui'
import { equipmentTypePath } from '@/config/routes'
import { fieldErrorsOf } from '@/lib/api'

import type { EquipmentType } from '../api'
import { inputFromForm } from '../equipmentTypeForm'
import { useUpdateEquipmentType } from '../hooks'

import { EquipmentTypeFields } from './EquipmentTypeFields'

/**
 * An equipment type, filled in with what it holds (SCRUM-27 AC1). Saving sends every field again,
 * then opens the type's page with what the backend saved; a refusal shows the backend's messages.
 */
export function EditEquipmentTypeForm({ type }: { type: EquipmentType }) {
  const update = useUpdateEquipmentType()
  const navigate = useNavigate()
  const typePath = equipmentTypePath(type.id)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const changes = inputFromForm(new FormData(event.currentTarget))
    update.mutate(
      { equipmentTypeId: String(type.id), changes },
      { onSuccess: () => void navigate(typePath) },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-8">
      <ErrorAlert error={update.error} />
      <EquipmentTypeFields fieldErrors={fieldErrorsOf(update.error)} initial={type} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" isPending={update.isPending}>
          Save changes
        </Button>
        <ButtonLink to={typePath} variant="ghost">
          Cancel
        </ButtonLink>
      </div>
    </form>
  )
}
