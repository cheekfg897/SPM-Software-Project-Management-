import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { selectSessionUser, useAppSelector } from '@/store'

import {
  eventRequestKeys,
  fetchEventRequest,
  fetchMyEventRequests,
  saveDraftEventRequest,
  submitDraftEventRequest,
  submitEventRequest,
  updateDraftEventRequest,
} from './api'
import type { EventRequestDetails } from './api'

/** The signed-in organiser's event requests, read for whoever is signed in. */
export function useMyEventRequests() {
  const viewer = useAppSelector(selectSessionUser)
  return useQuery({
    queryKey: eventRequestKeys.mine(viewer?.id ?? null),
    queryFn: fetchMyEventRequests,
  })
}

/** Read the organiser's list again once a request is saved or submitted. */
function useRefreshMyRequests() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: eventRequestKeys.all })
}

/**
 * Submit a new request (SCRUM-19). Afterwards the organiser's list is read again, so the new
 * request, its status and reference come from the backend.
 */
export function useSubmitEventRequest() {
  const refresh = useRefreshMyRequests()
  return useMutation({ mutationFn: submitEventRequest, onSuccess: refresh })
}

/** Save a new draft (SCRUM-20 AC1). */
export function useSaveDraftEventRequest() {
  const refresh = useRefreshMyRequests()
  return useMutation({ mutationFn: saveDraftEventRequest, onSuccess: refresh })
}

interface DraftChanges {
  reference: string
  changes: EventRequestDetails
}

/** Save the changes made to one of the organiser's drafts (SCRUM-20 AC3). */
export function useUpdateDraftEventRequest() {
  const refresh = useRefreshMyRequests()
  return useMutation({
    mutationFn: ({ reference, changes }: DraftChanges) =>
      updateDraftEventRequest(reference, changes),
    onSuccess: refresh,
  })
}

/**
 * Save the changes made to a draft, then submit it. The backend submits what a draft holds, so
 * the changes go first; a refusal of either shows as it comes back (SCRUM-20, ADR-0024).
 */
export function useSubmitDraftEventRequest() {
  const refresh = useRefreshMyRequests()
  return useMutation({
    mutationFn: async ({ reference, changes }: DraftChanges) => {
      await updateDraftEventRequest(reference, changes)
      return submitDraftEventRequest(reference)
    },
    onSuccess: refresh,
  })
}

/** One request's record, read for whoever is signed in: who may open it depends on them. */
export function useEventRequest(reference: string) {
  const viewer = useAppSelector(selectSessionUser)
  return useQuery({
    /* v8 ignore next -- its pages are for signed-in organisers and coordinators only (RequireRole), so a viewer is always there */
    queryKey: eventRequestKeys.one(reference, viewer?.id ?? null),
    queryFn: () => fetchEventRequest(reference),
  })
}
