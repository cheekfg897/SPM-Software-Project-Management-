import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  equipmentKeys,
  fetchEventAvailability,
  fetchEventReservations,
  reserveEquipment,
} from './api'
import type { ReserveEquipmentBody } from './api'

/** What is free of each equipment type for the event's period, with any shortfall. */
export function useEventAvailability(reference: string) {
  return useQuery({
    queryKey: equipmentKeys.availability(reference),
    queryFn: () => fetchEventAvailability(reference),
  })
}

/** The equipment already reserved for the event. */
export function useEventReservations(reference: string) {
  return useQuery({
    queryKey: equipmentKeys.reservations(reference),
    queryFn: () => fetchEventReservations(reference),
  })
}

/**
 * Reserve equipment for the event. Afterwards availability and the reservation list are read
 * again, so what is left comes from the backend rather than being worked out here.
 */
export function useReserveEquipment(reference: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ReserveEquipmentBody) => reserveEquipment(reference, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: equipmentKeys.event(reference) }),
  })
}
