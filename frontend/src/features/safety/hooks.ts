import { useQuery } from '@tanstack/react-query'

import { fetchAwaitingSafetyReview, safetyKeys } from './api'

/** The events awaiting the safety check, soonest first (SCRUM-97 AC5). */
export function useAwaitingSafetyReview() {
  return useQuery({ queryKey: safetyKeys.awaiting(), queryFn: fetchAwaitingSafetyReview })
}
