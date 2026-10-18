import { errorMessageOf, fieldErrorsOf } from '@/lib/api'

interface ErrorAlertProps {
  /** A query or mutation error. Nothing is shown while it is null. */
  error: unknown
}

/** The alert box: the backend's message, and under it every reason given, in order. */
function AlertBox({ message, reasons }: { message: string; reasons: string[] }) {
  return (
    <div
      role="alert"
      className="border-danger/40 bg-danger/10 text-danger rounded-xl border px-4 py-3 text-sm"
    >
      <p>{message}</p>
      {reasons.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Shows the backend's message for a failed request. A form shows its field messages itself. */
export function ErrorAlert({ error }: ErrorAlertProps) {
  if (error === null || error === undefined) {
    return null
  }
  return <AlertBox message={errorMessageOf(error)} reasons={[]} />
}

/**
 * Shows the backend's message for a refusal whose `details` are reasons, such as the gaps
 * holding an event back, and lists every one under it in the backend's order (ADR-0075).
 */
export function RefusalAlert({ error }: ErrorAlertProps) {
  if (error === null || error === undefined) {
    return null
  }
  const reasons = Object.values(fieldErrorsOf(error)).flat()
  return <AlertBox message={errorMessageOf(error)} reasons={reasons} />
}
