import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ROLE } from '@/config/roles'
import { selectSessionUser, useAppSelector } from '@/store'

import {
  createVenue,
  deactivateVenue,
  fetchVenue,
  fetchVenues,
  reactivateVenue,
  updateVenue,
  venueKeys,
} from './api'
import type { VenueDetails } from './api'

/** Every venue query is read again after a change, so the list and each page agree (AC3). */
function useInvalidateVenues() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: venueKeys.all })
}

/**
 * Whether the signed-in user keeps the catalogue (SCRUM-25 AC4), so the pages offer them its
 * actions. The backend still refuses anyone else who tries.
 */
export function useIsVenueStaff(): boolean {
  return useAppSelector(selectSessionUser)?.role === ROLE.VENUE_STAFF
}

/** The active venues, in the backend's order. */
export function useVenues() {
  return useQuery({ queryKey: venueKeys.list(), queryFn: fetchVenues })
}

export function useVenue(venueId: number) {
  return useQuery({ queryKey: venueKeys.detail(venueId), queryFn: () => fetchVenue(venueId) })
}

export function useCreateVenue() {
  const invalidateVenues = useInvalidateVenues()
  return useMutation({ mutationFn: createVenue, onSuccess: invalidateVenues })
}

export function useUpdateVenue(venueId: number) {
  const invalidateVenues = useInvalidateVenues()
  return useMutation({
    mutationFn: (changes: VenueDetails) => updateVenue(venueId, changes),
    onSuccess: invalidateVenues,
  })
}

export function useDeactivateVenue(venueId: number) {
  const invalidateVenues = useInvalidateVenues()
  return useMutation({ mutationFn: () => deactivateVenue(venueId), onSuccess: invalidateVenues })
}

export function useReactivateVenue(venueId: number) {
  const invalidateVenues = useInvalidateVenues()
  return useMutation({ mutationFn: () => reactivateVenue(venueId), onSuccess: invalidateVenues })
}
