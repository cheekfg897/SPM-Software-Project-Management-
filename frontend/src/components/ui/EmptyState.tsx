import type { ReactNode } from 'react'

interface EmptyStateProps {
  message: string
  /** An action to take instead, shown under the message. */
  children?: ReactNode
}

/** What a list shows when there is nothing in it. */
export function EmptyState({ message, children }: EmptyStateProps) {
  return (
    <div className="border-line rounded-2xl border border-dashed px-6 py-16 text-center">
      <p className="text-ink-muted">{message}</p>
      {children}
    </div>
  )
}
