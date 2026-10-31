import { ButtonLink } from '@/components/ui'
import { suggestionRequestPath } from '@/config/routes'

import type { BookingRequest } from '../api'
import { suggestionText } from '../suggestion'

interface SuggestedAlternativeProps {
  reference: string
  request: BookingRequest
}

/**
 * The alternative Venue Staff suggested when they rejected the request, beside its reason
 * (SCRUM-70 AC3), and a way to raise a new request from it (AC4). The venue is named by its id,
 * as the list names the request's own. Nothing when they suggested none.
 */
export function SuggestedAlternative({ reference, request }: SuggestedAlternativeProps) {
  const venueId = request.suggested_venue_id
  const text = suggestionText(
    venueId === null ? null : `Venue ${String(venueId)}`,
    request.suggested_starts_at,
    request.suggested_ends_at,
  )
  if (text === null) {
    return null
  }
  return (
    <div className="border-line mt-3 space-y-2 rounded-xl border p-3">
      <p className="text-ink">Venue Staff suggest instead: {text}</p>
      <ButtonLink
        to={suggestionRequestPath(reference, request.id)}
        variant="secondary"
        aria-label={`Raise a request from the suggestion for ${request.purpose}`}
      >
        Raise a request from this suggestion
      </ButtonLink>
    </div>
  )
}
