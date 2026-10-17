import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ROLE } from '@/config/roles'
import { selectSessionUser, useAppSelector } from '@/store'

import {
  blockVenue,
  createVenue,
  deactivateVenue,
  fetchVenue,
  fetchVenueBlocks,
  fetchVenueCalendar,
  fetchVenues,
  reactivateVenue,
  removeVenueBlock,
  updateVenue,
  venueKeys,
} from './api'
import type { CalendarRange, Deactivation, NewBlock, VenueDetails } from './api'

/**
 * Every venue query is read again after a change, so the list, each page, its blocks and its
 * calendar agree with the backend (SCRUM-25 AC3, SCRUM-34 AC1 and AC4).
 */
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
  return useMutation({
    mutationFn: (deactivation: Deactivation) => deactivateVenue(venueId, deactivation),
    onSuccess: invalidateVenues,
  })
}

export function useReactivateVenue(venueId: number) {
  const invalidateVenues = useInvalidateVenues()
  return useMutation({ mutationFn: () => reactivateVenue(venueId), onSuccess: invalidateVenues })
}

/** The venue's blocks, with their ids and reasons, to find one to remove (Venue Staff only). */
export function useVenueBlocks(venueId: number) {
  return useQuery({
    queryKey: venueKeys.blocks(venueId),
    queryFn: () => fetchVenueBlocks(venueId),
  })
}

/** Block the venue; its blocks and calendar are read again afterwards (SCRUM-34 AC1). */
export function useBlockVenue(venueId: number) {
  const invalidateVenues = useInvalidateVenues()
  return useMutation({
    mutationFn: (block: NewBlock) => blockVenue(venueId, block),
    onSuccess: invalidateVenues,
  })
}

/** Remove a block, freeing the period at once (SCRUM-34 AC4). */
export function useRemoveVenueBlock(venueId: number) {
  const invalidateVenues = useInvalidateVenues()
  return useMutation({
    mutationFn: (blockId: number) => removeVenueBlock(venueId, blockId),
    onSuccess: invalidateVenues,
  })
}

/**
 * The venue's unavailable periods in a range (SCRUM-26). How much each reason says depends on
 * who asks (AC3), so the key holds the viewer: signing in as someone else reads it again.
 */
export function useVenueCalendar(venueId: number, range: CalendarRange) {
  const viewerId = useAppSelector(selectSessionUser)?.id ?? null
  return useQuery({
    queryKey: venueKeys.calendar(venueId, range, viewerId),
    queryFn: () => fetchVenueCalendar(venueId, range),
  })
}
