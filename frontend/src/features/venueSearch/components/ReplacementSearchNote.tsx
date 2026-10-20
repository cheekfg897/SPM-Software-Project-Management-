import { Link } from 'react-router'

import { venueRequestsPath } from '@/config/routes'

import { useReplacementSearch } from '../hooks'

/**
 * Says the search is for a replacement venue, for which event, and leads back to its venue
 * requests (SCRUM-92 AC6). Nothing in an ordinary search.
 */
export function ReplacementSearchNote() {
  const replacement = useReplacementSearch()

  if (replacement === null) {
    return null
  }
  return (
    <p className="border-line bg-surface-raised text-ink mt-8 rounded-xl border p-4 text-sm">
      Finding a replacement venue for event {replacement.reference}. Choose one of the venues that
      match to request it.{' '}
      <Link to={venueRequestsPath(replacement.reference)} className="text-flare underline">
        Back to its venue requests
      </Link>
    </p>
  )
}
