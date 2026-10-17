import { useNavigate } from 'react-router'

import { Button, ButtonLink } from '@/components/ui'
import { venuePath } from '@/config/routes'

import type { UpdatedVenue, Venue } from '../api'
import { useUpdateVenue } from '../hooks'

import { OverlapReport } from './OverlapReport'
import { VenueForm } from './VenueForm'

/** Whether a saved change made any confirmed booking overlap something (ADR-0033). */
function hasOverlaps(saved: UpdatedVenue): boolean {
  return saved.overlap_warnings.length > 0 || saved.block_overlap_warnings.length > 0
}

/**
 * The venue's details to change (SCRUM-25 AC1, SCRUM-67 AC1). Every field is sent, so an emptied
 * required one is refused by the backend rather than kept (ADR-0053). Once saved, it goes back
 * to the venue's page, which shows the change, unless a new setup or turnaround time made
 * bookings overlap: then it shows what the backend reported first (SCRUM-67 AC4).
 */
export function EditVenueForm({ venue }: { venue: Venue }) {
  const update = useUpdateVenue(venue.id)
  const navigate = useNavigate()
  const venuePage = venuePath(venue.id)

  function goBackUnlessOverlapping(saved: UpdatedVenue) {
    if (!hasOverlaps(saved)) {
      void navigate(venuePage)
    }
  }

  if (update.data !== undefined && hasOverlaps(update.data)) {
    return <OverlapReport saved={update.data} />
  }
  return (
    <VenueForm
      initial={venue}
      error={update.error}
      onSubmit={(changes) => update.mutate(changes, { onSuccess: goBackUnlessOverlapping })}
    >
      <Button type="submit" isPending={update.isPending}>
        Save changes
      </Button>
      <ButtonLink to={venuePage} variant="ghost">
        Cancel
      </ButtonLink>
    </VenueForm>
  )
}
