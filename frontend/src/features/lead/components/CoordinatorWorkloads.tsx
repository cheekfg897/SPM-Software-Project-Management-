import { EmptyState } from '@/components/ui'

import type { Workload } from '../api'
import { useCoordinatorWorkload } from '../hooks'

import { QueryResult } from './QueryResult'
import { WorkloadCard } from './WorkloadCard'

function WorkloadGrid({ coordinators, message }: Workload) {
  // The backend sends a message only when no coordinator is listed (SCRUM-24 AC11, ADR-0041).
  if (message !== undefined) {
    return <EmptyState message={message} />
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {/* By position: the backend sends no ids, and two coordinators may share a name. */}
      {coordinators.map((workload, index) => (
        <WorkloadCard key={index} workload={workload} />
      ))}
    </div>
  )
}

/** Each coordinator the backend lists, in its order, with the active events they hold. */
export function CoordinatorWorkloads() {
  const workload = useCoordinatorWorkload()
  return (
    <QueryResult query={workload} loadingLabel="Loading the workload…">
      {(body) => <WorkloadGrid {...body} />}
    </QueryResult>
  )
}
