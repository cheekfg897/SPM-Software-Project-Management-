import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { formText } from '@/features/auth/formText'
import { fieldErrorsOf } from '@/lib/api'

import type { NewClientOrganisation } from '../api'
import { useCreateOrganisation } from '../hooks'

/** The organisation for the backend; an empty phone is left out, as it is optional. */
function organisationFrom(form: FormData): NewClientOrganisation {
  const organisation: NewClientOrganisation = {
    name: formText(form, 'name'),
    contact_name: formText(form, 'contact_name'),
    contact_email: formText(form, 'contact_email'),
  }
  const phone = formText(form, 'contact_phone')
  if (phone !== '') {
    organisation.contact_phone = phone
  }
  return organisation
}

/**
 * Record a client organisation (SCRUM-66 AC1). Once the backend saves it, the form clears and
 * says the organisation's ID, which its Event Organisers need to sign up.
 */
export function NewOrganisationForm() {
  const create = useCreateOrganisation()
  const fieldErrors = fieldErrorsOf(create.error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    create.mutate(organisationFrom(new FormData(form)), { onSuccess: () => form.reset() })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {create.data !== undefined && (
        <p
          role="status"
          className="border-success/30 bg-success/10 text-success rounded-xl border px-4 py-3 text-sm"
        >
          Recorded {create.data.name}. Its organisation ID is {create.data.id}: give it to the
          organisation’s Event Organisers so they can sign up.
        </p>
      )}
      <ErrorAlert error={create.error} />
      <TextField label="Organisation name" name="name" required errors={fieldErrors.name} />
      <TextField
        label="Contact name"
        name="contact_name"
        required
        errors={fieldErrors.contact_name}
      />
      <TextField
        label="Contact email"
        name="contact_email"
        type="email"
        required
        errors={fieldErrors.contact_email}
      />
      <TextField
        label="Contact phone"
        name="contact_phone"
        type="tel"
        hint="Optional."
        errors={fieldErrors.contact_phone}
      />
      <Button type="submit" isPending={create.isPending}>
        Record organisation
      </Button>
    </form>
  )
}
