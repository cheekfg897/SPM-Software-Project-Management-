import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  bookingKeys,
  decideBookingRequest,
  fetchBookingRequests,
  fetchPendingBookingRequests,
  raiseBookingRequest,
} from './api'
import type { BookingDecision, RaiseBookingRequest } from './api'

/** The booking requests raised for one of the coordinator's events. */
export function useBookingRequests(reference: string) {
  return useQuery({
    queryKey: bookingKeys.forEvent(reference),
    queryFn: () => fetchBookingRequests(reference),
  })
}

/** Raise a request for the event. Afterwards its list is read again, not patched by hand. */
export function useRaiseBookingRequest(reference: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: RaiseBookingRequest) => raiseBookingRequest(reference, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: bookingKeys.forEvent(reference) }),
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
