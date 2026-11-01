import type { Fact } from '../eventHistory'

/** Facts as a list of labels and values, e.g. a history entry's or a change request's. */
export function FactList({ facts }: { facts: Fact[] }) {
  return (
    <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[minmax(0,10rem)_1fr]">
      {facts.map(({ label, value }) => (
        <div key={label} className="contents">
          <dt className="text-ink-muted">{label}</dt>
          <dd className="text-ink whitespace-pre-line">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
