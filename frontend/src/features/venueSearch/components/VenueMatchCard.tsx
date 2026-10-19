import { useId } from 'react'

import { Badge, ButtonLink } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { replacementRequestPath } from '@/config/routes'

import type { MatchedRequirements, VenueMatch } from '../api'
import { useReplacementSearch } from '../hooks'

function Detail({ term, children }: { term: string; children: string | number }) {
  return (
    <div>
      <dt className="text-ink-faint text-xs tracking-wide uppercase">{term}</dt>
      <dd className="text-ink mt-0.5">{children}</dd>
    </div>
  )
}

/** The layout's name on screen, as the layout drop-down shows it. */
function layoutLabel(layout: string): string {
  const option = LAYOUT_OPTIONS.find((candidate) => candidate.value === layout)
  return `${option?.label ?? layout} layout`
}

/** Every requested requirement the venue meets, as the backend listed them (SCRUM-35 AC3). */
function metRequirements(matched: MatchedRequirements): string[] {
  const met: string[] = []
  if (matched.layout !== null) {
    met.push(layoutLabel(matched.layout))
  }
  met.push(...matched.facilities, ...matched.accessibility_features)
  return met
}

/**
 * One venue the search found: its name, capacity and location, its id for the venue request
 * form (SCRUM-42), and what it meets of what was asked for. In a search for a replacement it
 * also leads to requesting it as one (SCRUM-92).
 */
export function VenueMatchCard({ venue }: { venue: VenueMatch }) {
  const headingId = useId()
  const met = metRequirements(venue.matched_requirements)
  const replacement = useReplacementSearch()

  return (
    <article aria-labelledby={headingId} className="border-line bg-surface rounded-2xl border p-6">
      <h3 id={headingId} className="font-display text-xl font-semibold">
        {venue.name}
      </h3>
      <dl className="mt-4 grid gap-4 sm:grid-cols-3">
        <Detail term="Capacity">{venue.capacity}</Detail>
        <Detail term="Location">{venue.location}</Detail>
        <Detail term="Venue ID">{venue.id}</Detail>
      </dl>
      {met.length > 0 && (
        <ul aria-label="Meets" className="mt-4 flex flex-wrap gap-2">
          {/* By place: a facility and an accessibility need may read the same. */}
          {met.map((requirement, index) => (
            <li key={index}>
              <Badge>{requirement}</Badge>
            </li>
          ))}
        </ul>
      )}
      {replacement !== null && (
        <ButtonLink
          to={replacementRequestPath(replacement.reference, replacement.arrangementId, venue.id)}
          aria-label={`Request ${venue.name} as the replacement`}
          className="mt-5"
        >
          Request this venue
        </ButtonLink>
      )}
    </article>
  )
}
