import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { selectSessionUser, useAppSelector } from '@/store'

import {
  addEquipmentLine,
  equipmentKeys,
  fetchEventAvailability,
  fetchEventEquipmentLines,
  fetchEventReservations,
  recordEquipmentOutcome,
  removeEquipmentLine,
  reserveEquipment,
  updateEquipmentLine,
} from './api'
import type {
  EquipmentLineBody,
  EquipmentLineChange,
  EquipmentOutcomeChange,
  ReserveEquipmentBody,
} from './api'

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

/** The event's equipment lines, read for whoever is signed in. */
export function useEventEquipmentLines(reference: string) {
  const viewer = useAppSelector(selectSessionUser)
  return useQuery({
    queryKey: equipmentKeys.lines(reference, viewer?.id ?? null),
    queryFn: () => fetchEventEquipmentLines(reference),
  })
}

/**
 * Read all of the event's equipment again: its lines, availability (whose "requested" is the
 * lines' quantities) and reservations. Used after a change, refused or not: a refusal such as
 * "Only N available" or "already has a line for that equipment type" means someone else
 * changed it meanwhile, so the screen shows what the backend has now rather than a guess.
 */
function useRefreshEventEquipment(reference: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: equipmentKeys.event(reference) })
}

/** Reserve equipment for the event (SCRUM-46). */
export function useReserveEquipment(reference: string) {
  const refresh = useRefreshEventEquipment(reference)
  return useMutation({
    mutationFn: (body: ReserveEquipmentBody) => reserveEquipment(reference, body),
    onSettled: refresh,
  })
}

/** Add an equipment line to the event (SCRUM-37 AC1). */
export function useAddEquipmentLine(reference: string) {
  const refresh = useRefreshEventEquipment(reference)
  return useMutation({
    mutationFn: (body: EquipmentLineBody) => addEquipmentLine(reference, body),
    onSettled: refresh,
  })
}

/** Change one of the event's equipment lines (SCRUM-37 AC2). */
export function useUpdateEquipmentLine(reference: string) {
  const refresh = useRefreshEventEquipment(reference)
  return useMutation({
    mutationFn: (change: EquipmentLineChange) => updateEquipmentLine(reference, change),
    onSettled: refresh,
  })
}

/** Remove one of the event's equipment lines (SCRUM-37 AC2). */
export function useRemoveEquipmentLine(reference: string) {
  const refresh = useRefreshEventEquipment(reference)
  return useMutation({
    mutationFn: (lineId: number) => removeEquipmentLine(reference, lineId),
    onSettled: refresh,
  })
}

/** Record or revise the outcome of one of the event's lines (SCRUM-48). */
export function useRecordEquipmentOutcome(reference: string) {
  const refresh = useRefreshEventEquipment(reference)
  return useMutation({
    mutationFn: (change: EquipmentOutcomeChange) => recordEquipmentOutcome(reference, change),
    onSettled: refresh,
  })
}
