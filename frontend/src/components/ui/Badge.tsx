import type { ReactNode } from 'react'

interface BadgeProps {
  /** What is drawn in the badge, e.g. "Unread" or a count. */
  children: ReactNode
  /** What a screen reader says instead of the visible text, e.g. "3 unread notifications". */
  label?: string
}

/** A small pill that marks something, or carries a count. */
export function Badge({ children, label }: BadgeProps) {
  const classes =
    'bg-flare/15 text-flare inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold'
  if (label === undefined) {
    return <span className={classes}>{children}</span>
  }
  return (
    <span className={classes}>
      <span aria-hidden="true">{children}</span>
      <span className="sr-only">{label}</span>
    </span>
  )
}
