import type { ReactNode } from 'react'

import type { EquipmentType } from '../api'
import { locationText } from '../locationText'

import { DescriptionText } from './DescriptionText'

function Detail({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="py-4 sm:grid sm:grid-cols-3 sm:gap-4">
      <dt className="text-ink-muted text-sm font-medium">{term}</dt>
      <dd className="text-ink mt-1 sm:col-span-2 sm:mt-0">{children}</dd>
    </div>
  )
}

/** What the catalogue records about one type (SCRUM-27 AC1, AC2). */
export function EquipmentTypeDetails({ type }: { type: EquipmentType }) {
  return (
    <dl className="border-line/70 bg-surface/70 divide-line/70 max-w-2xl divide-y rounded-2xl border px-5">
      <Detail term="Description">
        <DescriptionText description={type.description} />
      </Detail>
      <Detail term="Total quantity held">{type.total_quantity}</Detail>
      <Detail term="Where it is kept">{locationText(type)}</Detail>
    </dl>
  )
}
