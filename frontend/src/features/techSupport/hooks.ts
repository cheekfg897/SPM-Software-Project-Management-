import { useQuery } from '@tanstack/react-query'

import { fetchEquipmentAwaitingAction, fetchEquipmentTypes, techSupportKeys } from './api'

/** The equipment still awaiting Technical Support, soonest event first (SCRUM-38). */
export function useEquipmentAwaitingAction() {
  return useQuery({
    queryKey: techSupportKeys.awaitingEquipment(),
    queryFn: fetchEquipmentAwaitingAction,
  })
}

/** Every equipment type, to name the queue's lines by (ADR-0022, ADR-0051). */
export function useEquipmentTypes() {
  return useQuery({
    queryKey: techSupportKeys.equipmentTypes(),
    queryFn: fetchEquipmentTypes,
  })
}
