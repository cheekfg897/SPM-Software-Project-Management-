import { Badge } from '@/components/ui'

import type { DescribedEntry } from '../eventHistory'

import { FactList } from './FactList'

/**
 * One history entry as eventHistory.ts words it: its title, a "Significant change" badge when
 * the backend marked it one (SCRUM-33 AC2), and its facts as a list of labels and values.
 */
export function DescribedEntryView({ described }: { described: DescribedEntry }) {
  const { title, isSignificant, facts } = described
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-ink font-medium">{title}</h3>
        {isSignificant && <Badge>Significant change</Badge>}
      </div>
      {facts.length > 0 && <FactList facts={facts} />}
    </>
  )
}
