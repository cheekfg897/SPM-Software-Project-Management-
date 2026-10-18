import { Badge } from '@/components/ui'

import type { DescribedEntry } from '../eventHistory'

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
      {facts.length > 0 && (
        <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[minmax(0,10rem)_1fr]">
          {facts.map(({ label, value }) => (
            <div key={label} className="contents">
              <dt className="text-ink-muted">{label}</dt>
              <dd className="text-ink whitespace-pre-line">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  )
}
