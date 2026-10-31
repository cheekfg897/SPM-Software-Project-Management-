import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'

import { Button, ErrorAlert, Spinner } from '@/components/ui'

interface BookingQueryListProps<Item> {
  /** One of Venue Staff's lists, as the backend sent it. */
  query: UseQueryResult<Item[]>
  /** What loading says, e.g. "Loading booking requests…". */
  loadingText: string
  /** What an empty list says. */
  emptyText: string
  /** The id that tells one item from the others. */
  itemKey: (item: Item) => number
  /** Draws one item. */
  children: (item: Item) => ReactNode
}

/**
 * One of Venue Staff's lists in the order the backend sent it, or its loading, error or empty
 * state in its place. The decisions queue, the flagged bookings (SCRUM-59) and the approved
 * bookings all use it.
 */
export function BookingQueryList<Item>({
  query,
  loadingText,
  emptyText,
  itemKey,
  children,
}: BookingQueryListProps<Item>) {
  if (query.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-3">
        <Spinner />
        {loadingText}
      </p>
    )
  }
  if (query.isError) {
    return (
      <div className="space-y-4">
        <ErrorAlert error={query.error} />
        <Button variant="secondary" onClick={() => void query.refetch()}>
          Try again
        </Button>
      </div>
    )
  }
  if (query.data.length === 0) {
    return (
      <p className="border-line text-ink-muted rounded-2xl border border-dashed px-6 py-16 text-center">
        {emptyText}
      </p>
    )
  }
  return (
    <ul className="space-y-5">
      {query.data.map((item) => (
        <li key={itemKey(item)}>{children(item)}</li>
      ))}
    </ul>
  )
}
