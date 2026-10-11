import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { assignCoordinator, fetchUnassignedQueue, leadKeys } from './api'

/** The requests waiting for the Lead to assign them, oldest first. */
export function useUnassignedQueue() {
  return useQuery({ queryKey: leadKeys.queue(), queryFn: fetchUnassignedQueue })
}

/**
 * Give a request to a coordinator. Afterwards the queue is read again, so the request
 * leaves it because the backend says so rather than because the cache was edited here.
 */
export function useAssignCoordinator() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: assignCoordinator,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: leadKeys.queue() }),
  })
}
