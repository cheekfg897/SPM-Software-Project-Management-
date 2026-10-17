import { useNavigate } from 'react-router'

import { PageContainer } from '@/components/layout'
import { Button } from '@/components/ui'
import { venuePath } from '@/config/routes'

import { VenueForm } from '../components/VenueForm'
import { useCreateVenue } from '../hooks'

/** Where Venue Staff add a venue to the catalogue (SCRUM-25 AC1); it opens once added. */
export function NewVenuePage() {
  const create = useCreateVenue()
  const navigate = useNavigate()

  return (
    <PageContainer
      title="Add a venue"
      description="Event Coordinators plan against what you record here, as soon as it's saved."
    >
      <VenueForm
        error={create.error}
        onSubmit={(details) =>
          create.mutate(details, { onSuccess: (venue) => void navigate(venuePath(venue.id)) })
        }
      >
        <Button type="submit" isPending={create.isPending}>
          Add venue
        </Button>
      </VenueForm>
    </PageContainer>
  )
}
