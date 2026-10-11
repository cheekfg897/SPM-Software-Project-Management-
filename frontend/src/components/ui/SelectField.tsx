import { useId } from 'react'
import type { SelectHTMLAttributes } from 'react'

export interface SelectOption {
  value: string
  label: string
}

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  name: string
  options: readonly SelectOption[]
  /** The backend's messages for this field, e.g. `fieldErrorsOf(error).required_layout`. */
  errors?: string[] | undefined
}

/** A labelled drop-down. Its first choice is empty, so the field can be left unanswered. */
export function SelectField({
  label,
  name,
  options,
  errors = [],
  className,
  ...rest
}: SelectFieldProps) {
  const selectId = useId()
  const errorsId = useId()
  const hasErrors = errors.length > 0

  return (
    <div className={className}>
      <label htmlFor={selectId} className="text-ink mb-1.5 block text-sm font-medium">
        {label}
      </label>
      <select
        id={selectId}
        name={name}
        aria-invalid={hasErrors}
        aria-describedby={hasErrors ? errorsId : undefined}
        className="border-line bg-surface text-ink focus:border-flare/70 aria-invalid:border-danger w-full rounded-xl border px-4 py-2.5 focus:outline-none"
        {...rest}
      >
        <option value="">No preference</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hasErrors && (
        <ul id={errorsId} className="text-danger mt-1.5 space-y-0.5 text-sm">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
