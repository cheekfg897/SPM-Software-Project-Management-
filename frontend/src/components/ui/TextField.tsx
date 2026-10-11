import type { InputHTMLAttributes } from 'react'

import { Field } from './Field'

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  name: string
  /** The backend's messages for this field, e.g. `fieldErrorsOf(error).email`. */
  errors?: string[] | undefined
  hint?: string
}

/** A labelled input that shows the backend's validation messages under it. */
export function TextField({ label, name, errors, hint, className, ...rest }: TextFieldProps) {
  return (
    <Field label={label} errors={errors} hint={hint} className={className}>
      {(control) => (
        <input
          {...control}
          name={name}
          className="border-line bg-surface text-ink placeholder:text-ink-faint focus:border-flare/70 aria-invalid:border-danger w-full rounded-xl border px-4 py-2.5 focus:outline-none"
          {...rest}
        />
      )}
    </Field>
  )
}
