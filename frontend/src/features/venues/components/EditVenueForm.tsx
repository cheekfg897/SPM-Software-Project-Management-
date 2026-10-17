import { useNavigate } from 'react-router'

import { Button, ButtonLink } from '@/components/ui'
import { venuePath } from '@/config/routes'

import type { Venue } from '../api'
import { useUpdateVenue } from '../hooks'

import { VenueForm } from './VenueForm'

/**
 * The venue's details to change (SCRUM-25 AC1, SCRUM-67 AC1). Every field is sent, so an emptied
 * required one is refused by the backend rather than kept (ADR-0053). Once saved, it goes back
 * to the venue's page, which shows the change.
 */
export function EditVenueForm({ venue }: { venue: Venue }) {
  const update = useUpdateVenue(venue.id)
  const navigate = useNavigate()
  const venuePage = venuePath(venue.id)

  return (
    <VenueForm
      initial={venue}
      error={update.error}
      onSubmit={(changes) => update.mutate(changes, { onSuccess: () => void navigate(venuePage) })}
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
