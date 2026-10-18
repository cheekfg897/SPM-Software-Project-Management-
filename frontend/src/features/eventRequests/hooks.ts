import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { selectSessionUser, useAppSelector } from '@/store'

import {
  answerClarification,
  decideEventRequest,
  eventRequestKeys,
  fetchAssignedEventRequests,
  fetchEventRequest,
  fetchEventRequestsWithEquipment,
  fetchMyEventRequests,
  requestClarification,
  saveDraftEventRequest,
  sendToSafetyReview,
  startEventRequestReview,
  submitDraftEventRequest,
  submitEventRequest,
  updateDraftEventRequest,
  WITH_EQUIPMENT_KEY,
} from './api'
import type { DecisionChoice, EventRequestDetails } from './api'

/** The signed-in organiser's event requests, read for whoever is signed in. */
export function useMyEventRequests() {
  const viewer = useAppSelector(selectSessionUser)
  return useQuery({
    queryKey: eventRequestKeys.mine(viewer?.id ?? null),
    queryFn: fetchMyEventRequests,
  })
}

/** The events assigned to the signed-in coordinator, read for whoever is signed in. */
export function useAssignedEventRequests() {
  const viewer = useAppSelector(selectSessionUser)
  return useQuery({
    /* v8 ignore next -- only a signed-in coordinator's Staff home asks for it (RequireRole), so a viewer is always there */
    queryKey: eventRequestKeys.assigned(viewer?.id ?? null),
    queryFn: fetchAssignedEventRequests,
  })
}

/**
 * Read every event-request query again after a change: the record and both role lists. Each
 * shows the change because the backend says so, not because the cache was edited here.
 */
function useRefreshEventRequests() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: eventRequestKeys.all })
}

/**
 * Submit a new request (SCRUM-19). Afterwards the organiser's list is read again, so the new
 * request, its status and reference come from the backend.
 */
export function useSubmitEventRequest() {
  const refresh = useRefreshEventRequests()
  return useMutation({ mutationFn: submitEventRequest, onSuccess: refresh })
}

/** Save a new draft (SCRUM-20 AC1). */
export function useSaveDraftEventRequest() {
  const refresh = useRefreshEventRequests()
  return useMutation({ mutationFn: saveDraftEventRequest, onSuccess: refresh })
}

interface DraftChanges {
  reference: string
  changes: EventRequestDetails
}

/** Save the changes made to one of the organiser's drafts (SCRUM-20 AC3). */
export function useUpdateDraftEventRequest() {
  const refresh = useRefreshEventRequests()
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
  const refresh = useRefreshEventRequests()
  return useMutation({
    mutationFn: async ({ reference, changes }: DraftChanges) => {
      await updateDraftEventRequest(reference, changes)
      return submitDraftEventRequest(reference)
    },
    onSuccess: refresh,
  })
}

/** Move a submitted request assigned to the coordinator to under review (SCRUM-31 AC3). */
export function useStartReview(reference: string) {
  const refresh = useRefreshEventRequests()
  return useMutation({ mutationFn: () => startEventRequestReview(reference), onSuccess: refresh })
}

/** Approve or reject a request assigned to the coordinator, or change its decision (SCRUM-31). */
export function useDecideEventRequest(reference: string) {
  const refresh = useRefreshEventRequests()
  return useMutation({
    mutationFn: (decision: DecisionChoice) => decideEventRequest(reference, decision),
    onSuccess: refresh,
  })
}

/** Ask the organiser a question about a request under review (SCRUM-32 AC1). */
export function useRequestClarification(reference: string) {
  const refresh = useRefreshEventRequests()
  return useMutation({
    mutationFn: (message: string) => requestClarification(reference, message),
    onSuccess: refresh,
  })
}

/** Answer the open question, sending the request back to review (SCRUM-32 AC2, ADR-0060). */
export function useAnswerClarification(reference: string) {
  const refresh = useRefreshEventRequests()
  return useMutation({
    mutationFn: (response: string) => answerClarification(reference, response),
    onSuccess: refresh,
  })
}

/** Send an approved event assigned to the coordinator to safety review (SCRUM-97). */
export function useSendToSafetyReview(reference: string) {
  const refresh = useRefreshEventRequests()
  return useMutation({ mutationFn: () => sendToSafetyReview(reference), onSuccess: refresh })
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

/** The events with an equipment request, for Technical Support's Staff home (SCRUM-24 AC5). */
export function useEventRequestsWithEquipment() {
  return useQuery({
    queryKey: WITH_EQUIPMENT_KEY,
    queryFn: fetchEventRequestsWithEquipment,
  })
}
