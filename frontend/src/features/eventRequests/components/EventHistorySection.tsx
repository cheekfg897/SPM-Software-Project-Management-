import { Badge, EmptyState, ErrorAlert, Spinner } from '@/components/ui'
import { formatDateTime } from '@/lib/formatDate'

import type { EventHistoryEntry } from '../api'
import { describeHistoryEntry } from '../eventHistory'
import { useEventHistory } from '../hooks'

import { RecordSection } from './RecordSection'

const NOTHING_YET = 'Nothing has been recorded for this event yet.'

/** e.g. "6 Oct, 2:00 pm · Leon Goh"; only when, for the system or someone whose account is gone. */
function whenAndWho({ occurred_at: occurredAt, actor_name: actorName }: EventHistoryEntry) {
  const when = formatDateTime(occurredAt)
  return actorName === null ? when : `${when} · ${actorName}`
}

/** One entry on the timeline: what happened, what its details say, then when and by whom. */
function HistoryItem({ entry }: { entry: EventHistoryEntry }) {
  const { title, isSignificant, facts } = describeHistoryEntry(entry)
  return (
    <li className="relative">
      <span
        aria-hidden="true"
        className="bg-flare absolute top-2 -left-[29px] size-2.5 rounded-full"
      />
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
      <p className="text-ink-faint mt-2 text-sm">{whenAndWho(entry)}</p>
    </li>
  )
}

function HistoryContent({ reference }: { reference: string }) {
  const history = useEventHistory(reference)
  if (history.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-2">
        <Spinner /> Loading the history…
      </p>
    )
  }
  if (history.isError) {
    return <ErrorAlert error={history.error} />
  }
  const entries = history.data.history
  if (entries.length === 0) {
    return <EmptyState message={NOTHING_YET} />
  }
  return (
    <ol className="border-line/60 ml-1 space-y-6 border-l pl-6">
      {entries.map((entry, index) => (
        // Entries from one edit share a time, and the list never reorders, so the place is the key.
        <HistoryItem key={`${entry.occurred_at}-${String(index)}`} entry={entry} />
      ))}
    </ol>
  )
}

/**
 * An event's history, oldest first, as the backend sends it to whoever is looking: all of it to
 * staff, and to an organiser without what is kept internal (SCRUM-33 AC4, AC5; ADR-0076).
 */
export function EventHistorySection({ reference }: { reference: string }) {
  return (
    <RecordSection title="History">
      <HistoryContent reference={reference} />
    </RecordSection>
  )
}
