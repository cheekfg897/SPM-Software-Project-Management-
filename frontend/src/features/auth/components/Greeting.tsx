import { ErrorAlert, Spinner } from '@/components/ui'

import { useCurrentUser } from '../hooks'

/** Greets the signed-in user by the name the backend has for them. */
export function Greeting() {
  const currentUser = useCurrentUser()

  if (currentUser.isPending) {
    return (
      <p className="text-ink-muted mt-8 flex items-center gap-2">
        <Spinner /> Loading your details…
      </p>
    )
  }
  if (currentUser.isError) {
    return (
      <div className="mt-8">
        <ErrorAlert error={currentUser.error} />
      </div>
    )
  }
  return <p className="mt-8 text-lg">Welcome back, {currentUser.data.full_name}.</p>
}
