import { errorMessageOf, fieldErrorsOf } from '@/lib/api'

interface ErrorAlertProps {
  /** A query or mutation error. Nothing is shown while it is null. */
  error: unknown
  /** What the message is about, when the alert stands apart from it, e.g. an event's name. */
  title?: string
}

interface AlertBoxProps {
  message: string
  reasons: string[]
  title?: string | undefined
}

/** The alert box: what it is about, the backend's message, and under it every reason, in order. */
function AlertBox({ message, reasons, title }: AlertBoxProps) {
  return (
    <div
      role="alert"
      className="border-danger/40 bg-danger/10 text-danger rounded-xl border px-4 py-3 text-sm"
    >
      {title !== undefined && <p className="font-semibold">{title}</p>}
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
export function ErrorAlert({ error, title }: ErrorAlertProps) {
  if (error === null || error === undefined) {
    return null
  }
  return <AlertBox message={errorMessageOf(error)} reasons={[]} title={title} />
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
