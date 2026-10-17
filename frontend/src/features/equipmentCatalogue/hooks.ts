import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  createEquipmentType,
  equipmentCatalogueKeys,
  fetchEquipmentType,
  fetchEquipmentTypes,
  updateEquipmentType,
} from './api'

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
