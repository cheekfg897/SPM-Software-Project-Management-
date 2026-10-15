import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { selectSessionUser, useAppSelector } from '@/store'

import { eventRequestKeys, fetchMyEventRequests, submitEventRequest } from './api'

/** The signed-in organiser's event requests, read for whoever is signed in. */
export function useMyEventRequests() {
  const viewer = useAppSelector(selectSessionUser)
  return useQuery({
    queryKey: eventRequestKeys.mine(viewer?.id ?? null),
    queryFn: fetchMyEventRequests,
  })
}

/**
 * Submit a new request (SCRUM-19). Afterwards the organiser's list is read again, so the new
 * request, its status and reference come from the backend.
 */
export function useSubmitEventRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: submitEventRequest,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: eventRequestKeys.all }),
  })
}
