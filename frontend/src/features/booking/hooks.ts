import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import type { PreparationUpdate } from '@/config/preparation'

import {
  bookingKeys,
  cancelAllArrangements,
  changeArrangement,
  changeHoldExpiry,
  decideBookingRequest,
  fetchApprovedBookingRequests,
  fetchBookingRequests,
  fetchPendingBookingRequests,
  placeBookingHold,
  raiseBookingRequest,
  updateBookingPreparation,
  withdrawArrangement,
} from './api'
import type {
  ArrangementChange,
  BookingDecision,
  BookingRequest,
  HoldExpiry,
  RaiseBookingRequest,
} from './api'
import { readReplacementRequest } from './replacement'

/**
 * What to run after a change to the event's requests: their list is read again, so it shows
 * what the backend now holds rather than a copy patched by hand.
 */
function useRereadEventRequests(reference: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: bookingKeys.forEvent(reference) })
}

/**
 * What to run after Venue Staff act on a request: their queue and their approved bookings are
 * read again, so a request leaves the queue, shows its new status, or moves down to the approved
 * bookings (SCRUM-84), because the backend says so.
 */
function useRereadQueue() {
  const queryClient = useQueryClient()
  return async () => {
    await queryClient.invalidateQueries({ queryKey: bookingKeys.pending() })
    await queryClient.invalidateQueries({ queryKey: bookingKeys.approved() })
  }
}

/** The booking requests raised for one of the coordinator's events. */
export function useBookingRequests(reference: string) {
  return useQuery({
    queryKey: bookingKeys.forEvent(reference),
    queryFn: () => fetchBookingRequests(reference),
  })
}

/**
 * The replacement the request form is raising, from the page URL, with the flagged arrangement
 * it replaces when the event's list holds it (SCRUM-92 AC6). Stopping drops it from the URL.
 */
export function useReplacementRequest(reference: string) {
  const [searchParams, setSearchParams] = useSearchParams()
  const requests = useBookingRequests(reference)
  const replacement = readReplacementRequest(searchParams)
  let replaced: BookingRequest | undefined
  if (replacement !== null) {
    replaced = requests.data?.find((arrangement) => arrangement.id === replacement.arrangementId)
  }

  return {
    replacement,
    replaced,
    stopReplacing: () => setSearchParams(new URLSearchParams()),
  }
}

/**
 * Raise a request for the event. The list is read again even after a refusal, which may come from
 * a change the page hasn't seen, such as a replaced arrangement's flag clearing (SCRUM-92).
 */
export function useRaiseBookingRequest(reference: string) {
  const reread = useRereadEventRequests(reference)
  return useMutation({
    mutationFn: (payload: RaiseBookingRequest) => raiseBookingRequest(reference, payload),
    onSettled: reread,
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
 * Approve or reject one request. Afterwards the queue and the approved bookings are read again,
 * so the request moves between them because the backend says so rather than because the cache
 * was edited here (SCRUM-84).
 */
export function useDecideBookingRequest(requestId: number) {
  const reread = useRereadQueue()
  return useMutation({
    mutationFn: (decision: BookingDecision) => decideBookingRequest(requestId, decision),
    onSuccess: reread,
  })
}

/** Hold the request's venue until an expiry (SCRUM-75). Afterwards the queue is read again. */
export function usePlaceBookingHold(requestId: number) {
  const reread = useRereadQueue()
  return useMutation({
    mutationFn: (hold: HoldExpiry) => placeBookingHold(requestId, hold),
    onSuccess: reread,
  })
}

/** Move the expiry of a request's hold (SCRUM-75 AC4). Afterwards the queue is read again. */
export function useChangeHoldExpiry(requestId: number) {
  const reread = useRereadQueue()
  return useMutation({
    mutationFn: (hold: HoldExpiry) => changeHoldExpiry(requestId, hold),
    onSuccess: reread,
  })
}

/** Every approved booking, for Venue Staff to prepare, earliest event first (SCRUM-84). */
export function useApprovedBookingRequests() {
  return useQuery({ queryKey: bookingKeys.approved(), queryFn: fetchApprovedBookingRequests })
}

/**
 * Record one booking's preparation. Afterwards the approved list is read again, so what it
 * shows is what the backend saved.
 */
export function useUpdateBookingPreparation(requestId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (update: PreparationUpdate) => updateBookingPreparation(requestId, update),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: bookingKeys.approved() }),
  })
}
