import type { ReactNode } from 'react'

import { ErrorAlert } from '@/components/ui'

import type { EquipmentType } from '../api'
import { useEquipmentType } from '../hooks'

import { LoadingStatus } from './LoadingStatus'

interface EquipmentTypeLoaderProps {
  equipmentTypeId: string
  /** Draws the page's content once the backend has sent the type. */
  children: (type: EquipmentType) => ReactNode
}

/** One equipment type once the backend has sent it, or the loading or error state in its place. */
export function EquipmentTypeLoader({ equipmentTypeId, children }: EquipmentTypeLoaderProps) {
  const type = useEquipmentType(equipmentTypeId)

  if (type.isPending) {
    return <LoadingStatus what="the equipment type" />
  }
  if (type.isError) {
    return <ErrorAlert error={type.error} />
  }
  return children(type.data)
}
