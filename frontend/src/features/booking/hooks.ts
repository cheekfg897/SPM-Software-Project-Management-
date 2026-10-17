import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  bookingKeys,
  cancelAllArrangements,
  changeArrangement,
  decideBookingRequest,
  fetchBookingRequests,
  fetchPendingBookingRequests,
  raiseBookingRequest,
  withdrawArrangement,
} from './api'
import type { ArrangementChange, BookingDecision, RaiseBookingRequest } from './api'

/**
 * What to run after a change to the event's requests: their list is read again, so it shows
 * what the backend now holds rather than a copy patched by hand.
 */
function useRereadEventRequests(reference: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: bookingKeys.forEvent(reference) })
}

/** The booking requests raised for one of the coordinator's events. */
export function useBookingRequests(reference: string) {
  return useQuery({
    queryKey: bookingKeys.forEvent(reference),
    queryFn: () => fetchBookingRequests(reference),
  })
}

/** Raise a request for the event. */
export function useRaiseBookingRequest(reference: string) {
  const reread = useRereadEventRequests(reference)
  return useMutation({
    mutationFn: (payload: RaiseBookingRequest) => raiseBookingRequest(reference, payload),
    onSuccess: reread,
  })
}

/** Change one of the event's pending arrangements (SCRUM-93). */
export function useChangeArrangement(reference: string, arrangementId: number) {
  const reread = useRereadEventRequests(reference)
  return useMutation({
    mutationFn: (change: ArrangementChange) => changeArrangement(reference, arrangementId, change),
    onSuccess: reread,
  })
}

/** Withdraw one of the event's arrangements, leaving the others as they are (SCRUM-93). */
export function useWithdrawArrangement(reference: string, arrangementId: number) {
  const reread = useRereadEventRequests(reference)
  return useMutation({
    mutationFn: () => withdrawArrangement(reference, arrangementId),
    onSuccess: reread,
  })
}

/** Withdraw every arrangement the event still has, in one go (SCRUM-93). */
export function useCancelAllArrangements(reference: string) {
  const reread = useRereadEventRequests(reference)
  return useMutation({
    mutationFn: () => cancelAllArrangements(reference),
    onSuccess: reread,
  })
}

/** The requests waiting for Venue Staff to decide, earliest event first (SCRUM-43). */
export function usePendingBookingRequests() {
  return useQuery({ queryKey: bookingKeys.pending(), queryFn: fetchPendingBookingRequests })
}

/**
 * Approve or reject one request. Afterwards the queue is read again, so the request leaves
 * it because the backend says so rather than because the cache was edited here.
 */
export function useDecideBookingRequest(requestId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (decision: BookingDecision) => decideBookingRequest(requestId, decision),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: bookingKeys.pending() }),
  })
}
