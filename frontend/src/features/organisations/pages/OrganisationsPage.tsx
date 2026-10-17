import { PageContainer } from '@/components/layout'
import { ErrorAlert, Spinner } from '@/components/ui'

import { NewOrganisationForm } from '../components/NewOrganisationForm'
import { OrganisationTable } from '../components/OrganisationTable'
import { useOrganisations } from '../hooks'

/** Staff record and list client organisations (SCRUM-66). Staff only (AC5). */
export function OrganisationsPage() {
  const organisations = useOrganisations()

  return (
    <PageContainer
      title="Client organisations"
      description="The organisations whose Event Organisers plan events with us. An organiser signs up with their organisation's ID."
    >
      <section className="mt-10 space-y-4" aria-labelledby="organisations-heading">
        <h2 id="organisations-heading" className="text-xl font-semibold">
          Organisations
        </h2>
        <ErrorAlert error={organisations.error} />
        {organisations.isPending && (
          <p className="text-ink-muted flex items-center gap-2">
            <Spinner />
            Loading client organisations
          </p>
        )}
        {organisations.data !== undefined && (
          <OrganisationTable organisations={organisations.data} />
        )}
      </section>
      <section className="mt-12 max-w-xl space-y-4" aria-labelledby="record-heading">
        <h2 id="record-heading" className="text-xl font-semibold">
          Record an organisation
        </h2>
        <NewOrganisationForm />
      </section>
    </PageContainer>
  )
}
