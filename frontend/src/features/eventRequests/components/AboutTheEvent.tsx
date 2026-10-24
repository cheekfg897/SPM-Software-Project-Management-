import type { EventRequest } from '../api'

/** The organiser's answers, each against its label, leaving out the ones not given. */
function detailsOf(record: EventRequest): [string, string][] {
  const details: [string, string][] = []
  if (record.expected_attendance !== null) {
    details.push(['Expected attendance', String(record.expected_attendance)])
  }
  const written: [string, string | null][] = [
    ['Purpose', record.purpose],
    ['Description', record.description],
    ['Venue requirements', record.venue_requirements],
    ['Accessibility needs', record.accessibility_needs],
    ['Equipment requirements', record.equipment_requirements],
  ]
  for (const [label, value] of written) {
    if (value !== null) {
      details.push([label, value])
    }
  }
  details.push(['Registration', record.registration_required ? 'Needed' : 'Not needed'])
  return details
}

/** The event's details as its organiser gave them, on every view of its record (ADR-0056). */
export function AboutTheEvent({ record }: { record: EventRequest }) {
  return (
    <dl className="border-line/60 bg-surface/50 divide-line/60 divide-y rounded-2xl border">
      {detailsOf(record).map(([label, value]) => (
        <div key={label} className="grid gap-1 px-5 py-4 sm:grid-cols-3 sm:gap-4">
          <dt className="text-ink-muted text-sm">{label}</dt>
          <dd className="text-ink whitespace-pre-line sm:col-span-2">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
