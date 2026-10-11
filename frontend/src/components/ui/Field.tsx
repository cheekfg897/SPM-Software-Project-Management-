import { useId } from 'react'
import type { ReactNode } from 'react'

/** What a control needs to be tied to its label, hint and error messages. */
export interface FieldControlProps {
  id: string
  'aria-invalid': boolean
  'aria-describedby': string | undefined
}

interface FieldProps {
  label: string
  /** The backend's messages for this field, e.g. `fieldErrorsOf(error).email`. */
  errors?: string[] | undefined
  /** Shown under the control while there are no errors. */
  hint?: string | undefined
  className?: string | undefined
  /** Draws the control, given the props that wire it to the label and messages. */
  children: (control: FieldControlProps) => ReactNode
}

/**
 * A control's label, its hint and the backend's validation messages under it. The control
 * itself (an input, a select) is drawn by `children`, so every field is labelled, described
 * and flagged invalid in this one place.
 */
export function Field({ label, errors = [], hint, className, children }: FieldProps) {
  const controlId = useId()
  const descriptionId = useId()
  const hasErrors = errors.length > 0
  const hasDescription = hasErrors || hint !== undefined

  return (
    <div className={className}>
      <label htmlFor={controlId} className="text-ink mb-1.5 block text-sm font-medium">
        {label}
      </label>
      {children({
        id: controlId,
        'aria-invalid': hasErrors,
        'aria-describedby': hasDescription ? descriptionId : undefined,
      })}
      {hasErrors && (
        <ul id={descriptionId} className="text-danger mt-1.5 space-y-0.5 text-sm">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      {!hasErrors && hint !== undefined && (
        <p id={descriptionId} className="text-ink-faint mt-1.5 text-sm">
          {hint}
        </p>
      )}
    </div>
  )
}
