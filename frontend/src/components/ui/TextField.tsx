import { useId } from 'react'
import type { InputHTMLAttributes } from 'react'

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  name: string
  /** The backend's messages for this field, e.g. `fieldErrorsOf(error).email`. */
  errors?: string[] | undefined
  hint?: string
}

/** A labelled input that shows the backend's validation messages under it. */
export function TextField({ label, name, errors = [], hint, className, ...rest }: TextFieldProps) {
  const inputId = useId()
  const descriptionId = useId()
  const hasErrors = errors.length > 0
  const hasDescription = hasErrors || hint !== undefined

  return (
    <div className={className}>
      <label htmlFor={inputId} className="text-ink mb-1.5 block text-sm font-medium">
        {label}
      </label>
      <input
        id={inputId}
        name={name}
        aria-invalid={hasErrors}
        aria-describedby={hasDescription ? descriptionId : undefined}
        className="border-line bg-surface text-ink placeholder:text-ink-faint focus:border-flare/70 aria-invalid:border-danger w-full rounded-xl border px-4 py-2.5 focus:outline-none"
        {...rest}
      />
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
