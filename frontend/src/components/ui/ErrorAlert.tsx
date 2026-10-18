import { errorMessageOf, fieldErrorsOf } from '@/lib/api'

interface ErrorAlertProps {
  /** A query or mutation error. Nothing is shown while it is null. */
  error: unknown
  /**
   * Also list every message in the error's `details`, in the backend's order: for a refusal
   * whose details are reasons, such as the gaps holding an event back (ADR-0075). Left off, a
   * form shows those messages under its fields instead.
   */
  listDetails?: boolean
}

/** Shows the backend's message for a failed request. */
export function ErrorAlert({ error, listDetails = false }: ErrorAlertProps) {
  if (error === null || error === undefined) {
    return null
  }
  const details = listDetails ? Object.values(fieldErrorsOf(error)).flat() : []
  return (
    <div
      role="alert"
      className="border-danger/40 bg-danger/10 text-danger rounded-xl border px-4 py-3 text-sm"
    >
      <p>{errorMessageOf(error)}</p>
      {details.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {details.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
