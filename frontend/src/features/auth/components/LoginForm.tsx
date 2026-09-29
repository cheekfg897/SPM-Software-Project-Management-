import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import { formText } from '../formText'
import { useLogIn } from '../hooks'

/** Email and password, for both log-in pages. The page redirects once it succeeds. */
export function LoginForm() {
  const logIn = useLogIn()
  const fieldErrors = fieldErrorsOf(logIn.error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    logIn.mutate({ email: formText(form, 'email'), password: formText(form, 'password') })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <ErrorAlert error={logIn.error} />
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
        autoComplete="current-password"
        required
        errors={fieldErrors.password}
      />
      <Button type="submit" isPending={logIn.isPending} className="w-full">
        Log in
      </Button>
    </form>
  )
}
