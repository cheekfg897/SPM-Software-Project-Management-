import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { bookingKeys, fetchBookingRequests, raiseBookingRequest } from './api'
import type { RaiseBookingRequest } from './api'

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
