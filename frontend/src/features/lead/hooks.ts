import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  assignCoordinator,
  fetchActiveEvents,
  fetchCoordinatorWorkload,
  fetchUnassignedQueue,
  leadKeys,
  reassignCoordinator,
} from './api'

/** The requests waiting for the Lead to assign them, oldest first. */
export function useUnassignedQueue() {
  return useQuery({ queryKey: leadKeys.queue(), queryFn: fetchUnassignedQueue })
}

/** Every active event with its status and coordinator, newest first (SCRUM-96 AC1). */
export function useActiveEvents() {
  return useQuery({ queryKey: leadKeys.active(), queryFn: fetchActiveEvents })
}

/** Every Event Coordinator, with their active events and how many (SCRUM-96 AC3). */
export function useCoordinatorWorkload() {
  return useQuery({ queryKey: leadKeys.workload(), queryFn: fetchCoordinatorWorkload })
}

/**
 * Give a request to a coordinator. Afterwards every Lead list is read again: the request leaves
 * the queue and joins the coordinator's workload because the backend says so, not because the
 * cache was edited here.
 */
export function useAssignCoordinator() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: assignCoordinator,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: leadKeys.all }),
  })
}

/** Move an event to another coordinator, then read the active list and the workload again. */
export function useReassignCoordinator() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: reassignCoordinator,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: leadKeys.oversight() }),
  })
}
