import { errorMessageOf } from '@/lib/api'

interface ErrorAlertProps {
  /** A query or mutation error. Nothing is shown while it is null. */
  error: unknown
}

/** Shows the backend's message for a failed request. */
export function ErrorAlert({ error }: ErrorAlertProps) {
  if (error === null || error === undefined) {
    return null
  }
  return (
    <p
      role="alert"
      className="border-danger/40 bg-danger/10 text-danger rounded-xl border px-4 py-3 text-sm"
    >
      {errorMessageOf(error)}
    </p>
  )
}
