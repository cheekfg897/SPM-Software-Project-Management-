import type { SelectHTMLAttributes } from 'react'

import { Field } from './Field'

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
  hint?: string
  /** What the empty first choice says. */
  emptyLabel?: string
}

/** A labelled drop-down. Its first choice is empty, so the field can be left unanswered. */
export function SelectField({
  label,
  name,
  options,
  errors,
  hint,
  emptyLabel = 'No preference',
  className,
  ...rest
}: SelectFieldProps) {
  return (
    <Field label={label} errors={errors} hint={hint} className={className}>
      {(control) => (
        <select
          {...control}
          name={name}
          className="border-line bg-surface text-ink focus:border-flare/70 aria-invalid:border-danger w-full rounded-xl border px-4 py-2.5 focus:outline-none"
          {...rest}
        >
          <option value="">{emptyLabel}</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  )
}
