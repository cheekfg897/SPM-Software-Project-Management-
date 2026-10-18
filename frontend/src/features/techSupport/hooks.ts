import { useQuery } from '@tanstack/react-query'

import { fetchEquipmentAwaitingAction, techSupportKeys } from './api'

/** The equipment still awaiting Technical Support, soonest event first (SCRUM-38). */
export function useEquipmentAwaitingAction() {
  return useQuery({
    queryKey: techSupportKeys.awaitingEquipment(),
    queryFn: fetchEquipmentAwaitingAction,
  })
}
