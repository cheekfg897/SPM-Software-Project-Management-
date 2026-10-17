import { useMutation, useMutationState, useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchAwaitingSafetyReview, recordSafetyOutcome, safetyKeys } from './api'
import type { RecordedSafetyOutcome, RecordSafetyOutcomeInput } from './api'

/** The events awaiting the safety check, soonest first (SCRUM-97 AC5). */
export function useAwaitingSafetyReview() {
  return useQuery({ queryKey: safetyKeys.awaiting(), queryFn: fetchAwaitingSafetyReview })
}

/**
 * Record one event's outcome. Afterwards the list is read again, so the event leaves it because
 * the backend says so rather than because the cache was edited here.
 */
export function useRecordSafetyOutcome() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: safetyKeys.outcome(),
    mutationFn: recordSafetyOutcome,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: safetyKeys.awaiting() }),
  })
}

export interface LatestOutcome {
  input: RecordSafetyOutcomeInput
  recorded: RecordedSafetyOutcome
}

/**
 * The outcome recorded last, or undefined before any. Read from TanStack's own record of the
 * outcome mutations, so the page can say what happened after the event's form has gone with it.
 */
export function useLatestOutcome(): LatestOutcome | undefined {
  const outcomes = useMutationState({
    filters: { mutationKey: safetyKeys.outcome(), status: 'success' },
    // Only useRecordSafetyOutcome uses this key, so these are its input and its answer.
    select: (mutation) => ({
      input: mutation.state.variables as RecordSafetyOutcomeInput,
      recorded: mutation.state.data as RecordedSafetyOutcome,
    }),
  })
  return outcomes.at(-1)
}
