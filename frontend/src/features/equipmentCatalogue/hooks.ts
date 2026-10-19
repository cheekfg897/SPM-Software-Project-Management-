import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { equipmentKeys } from '@/features/equipment/api'

import {
  createEquipmentType,
  equipmentCatalogueKeys,
  fetchEquipmentType,
  fetchEquipmentTypes,
  fetchOutOfService,
  returnToService,
  takeOutOfService,
  updateEquipmentType,
} from './api'
import type { OutOfServiceBody } from './api'

/** Every equipment type, as the backend lists them. The same for every member of staff. */
export function useEquipmentTypes() {
  return useQuery({ queryKey: equipmentCatalogueKeys.list(), queryFn: fetchEquipmentTypes })
}

/** One equipment type, by the id in the page's address. */
export function useEquipmentType(equipmentTypeId: string) {
  return useQuery({
    queryKey: equipmentCatalogueKeys.type(equipmentTypeId),
    queryFn: () => fetchEquipmentType(equipmentTypeId),
  })
}

/**
 * Read the catalogue again once a type is saved. The mutation waits for it, so the page opened
 * next shows what the backend saved rather than what was there before.
 */
function useRefreshCatalogue() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: equipmentCatalogueKeys.all })
}

/** Add an equipment type (SCRUM-27 AC1). */
export function useCreateEquipmentType() {
  const refresh = useRefreshCatalogue()
  return useMutation({ mutationFn: createEquipmentType, onSuccess: refresh })
}

/** Change an equipment type (SCRUM-27 AC1). */
export function useUpdateEquipmentType() {
  const refresh = useRefreshCatalogue()
  return useMutation({ mutationFn: updateEquipmentType, onSuccess: refresh })
}

/** The type's units still out of service (SCRUM-47). Technical Support Staff only. */
export function useOutOfService(equipmentTypeId: string) {
  return useQuery({
    queryKey: equipmentCatalogueKeys.outOfService(equipmentTypeId),
    queryFn: () => fetchOutOfService(equipmentTypeId),
  })
}

/**
 * Read the type's units out of service again, and every event's equipment: units going out or
 * coming back change what is available and which reservations are flagged (SCRUM-47 AC2, AC3).
 * Used after a refusal too, since "Only N units are in service." means someone else changed it.
 */
function useRefreshOutOfService(equipmentTypeId: string) {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({
        queryKey: equipmentCatalogueKeys.outOfService(equipmentTypeId),
      }),
      queryClient.invalidateQueries({ queryKey: equipmentKeys.all }),
    ])
}

/** Take units of the type out of service as damaged or under maintenance (SCRUM-47 AC1). */
export function useTakeOutOfService(equipmentTypeId: string) {
  const refresh = useRefreshOutOfService(equipmentTypeId)
  return useMutation({
    mutationFn: (body: OutOfServiceBody) => takeOutOfService({ equipmentTypeId, body }),
    onSettled: refresh,
  })
}

/** Put an entry's units of the type back in service, so they are Available again (SCRUM-47 AC1). */
export function useReturnToService(equipmentTypeId: string) {
  const refresh = useRefreshOutOfService(equipmentTypeId)
  return useMutation({ mutationFn: returnToService, onSettled: refresh })
}
