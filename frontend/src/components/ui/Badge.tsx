import type { ReactNode } from 'react'

interface BadgeProps {
  /** What is drawn in the badge, e.g. "Unread" or a count. */
  children: ReactNode
}

/** A small pill that marks something, or carries a count. */
export function Badge({ children }: BadgeProps) {
  return (
    <span className="bg-flare/15 text-flare inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold">
      {children}
    </span>
  )
}
