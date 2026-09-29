import { useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { ROLE } from '@/config/roles'
import { fieldErrorsOf } from '@/lib/api'

import type { Registration } from '../api'
import { formText } from '../formText'
import { useSignUp } from '../hooks'
import { AccountTypeChoice } from './AccountTypeChoice'
import type { AccountType } from './AccountTypeChoice'

/**
 * The organisation ID as the backend wants it: a JSON number, or null when left empty so the
 * backend can say an organiser needs one. Anything else is the backend's to refuse.
 */
function organisationIdFrom(typed: string): number | null {
  const trimmed = typed.trim()
  return trimmed === '' ? null : Number(trimmed)
}

function registrationFrom(form: FormData, accountType: AccountType): Registration {
  const registration: Registration = {
    full_name: formText(form, 'full_name'),
    email: formText(form, 'email'),
    password: formText(form, 'password'),
    role: accountType,
  }
  if (accountType === ROLE.EVENT_ORGANISER) {
    registration.organisation_id = organisationIdFrom(formText(form, 'organisation_id'))
  }
  return registration
}

/** Create an Event Organiser or Attendee account (SCRUM-65). The page redirects on success. */
export function SignUpForm() {
  const signUp = useSignUp()
  const [accountType, setAccountType] = useState<AccountType>(ROLE.ATTENDEE)
  const fieldErrors = fieldErrorsOf(signUp.error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    signUp.mutate(registrationFrom(new FormData(event.currentTarget), accountType))
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <ErrorAlert error={signUp.error} />
      <AccountTypeChoice value={accountType} onChange={setAccountType} />
      <TextField
        label="Full name"
        name="full_name"
        autoComplete="name"
        required
        errors={fieldErrors.full_name}
      />
      <TextField
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        required
        errors={fieldErrors.email}
      />
      <TextField
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        required
        errors={fieldErrors.password}
      />
      {accountType === ROLE.EVENT_ORGANISER && (
        <TextField
          label="Organisation ID"
          name="organisation_id"
          type="number"
          inputMode="numeric"
          min={1}
          hint="ConnectSphere staff give you this when they add your organisation."
          errors={fieldErrors.organisation_id}
        />
      )}
      <Button type="submit" isPending={signUp.isPending} className="w-full">
        Create account
      </Button>
    </form>
  )
}
