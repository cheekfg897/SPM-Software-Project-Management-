import type { TextareaHTMLAttributes } from 'react'

import { Field } from './Field'

interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string
  name: string
  /** The backend's messages for this field, e.g. `fieldErrorsOf(error).description`. */
  errors?: string[] | undefined
  hint?: string | undefined
}

/** A labelled multi-line text box that shows the backend's validation messages under it. */
export function TextAreaField({
  label,
  name,
  errors,
  hint,
  className,
  rows = 3,
  ...rest
}: TextAreaFieldProps) {
  return (
    <Field label={label} errors={errors} hint={hint} className={className}>
      {(control) => (
        <textarea
          {...control}
          name={name}
          rows={rows}
          className="border-line bg-surface text-ink placeholder:text-ink-faint focus:border-flare/70 aria-invalid:border-danger w-full resize-y rounded-xl border px-4 py-2.5 focus:outline-none"
          {...rest}
        />
      )}
    </Field>
  )
}
