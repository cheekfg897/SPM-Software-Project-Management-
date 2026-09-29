import { useId } from 'react'

export interface SegmentedOption<T extends string> {
  value: T
  label: string
}

interface SegmentedControlProps<T extends string> {
  /** The group's accessible name. */
  label: string
  options: readonly SegmentedOption<T>[]
  /** The checked option's value. A value matching no option checks nothing. */
  value: string
  onChange: (value: T) => void
}

/**
 * A row of mutually exclusive choices. Built from real radio inputs, so keyboard use and
 * screen readers work without extra code.
 */
export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
}: SegmentedControlProps<T>) {
  const groupName = useId()

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="border-line bg-surface inline-flex flex-wrap gap-1 rounded-full border p-1"
    >
      {options.map((option) => (
        <label key={option.value} className="relative shrink-0 cursor-pointer">
          <input
            type="radio"
            name={groupName}
            value={option.value}
            checked={option.value === value}
            onChange={() => onChange(option.value)}
            className="peer sr-only"
          />
          <span className="text-ink-muted peer-checked:bg-surface-raised peer-checked:text-ink peer-focus-visible:outline-flare hover:text-ink block rounded-full px-4 py-1.5 text-sm transition peer-checked:shadow-[inset_0_0_0_1px_var(--color-line)] peer-focus-visible:outline-2">
            {option.label}
          </span>
        </label>
      ))}
    </div>
  )
}
