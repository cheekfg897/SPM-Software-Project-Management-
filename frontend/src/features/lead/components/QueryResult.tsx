import type { UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { Button, ErrorAlert, Spinner } from '@/components/ui'

interface QueryResultProps<Data> {
  query: UseQueryResult<Data>
  /** Says what is loading, e.g. "Loading unassigned requests…". */
  loadingLabel: string
  /** Draws what the backend sent, once it has answered. */
  children: (data: Data) => ReactNode
}

/** One of the Lead's lists while it loads, when it fails (with a retry), and once it arrives. */
export function QueryResult<Data>({ query, loadingLabel, children }: QueryResultProps<Data>) {
  if (query.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-3">
        <Spinner />
        {loadingLabel}
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
  return <>{children(query.data)}</>
}
