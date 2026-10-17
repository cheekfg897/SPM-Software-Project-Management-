import { DataTable, EmptyState } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'

import type { ClientOrganisation } from '../api'

const COLUMNS: DataTableColumn<ClientOrganisation>[] = [
  { header: 'ID', cell: (organisation) => organisation.id },
  {
    header: 'Name',
    cell: (organisation) => <span className="text-ink font-medium">{organisation.name}</span>,
  },
  { header: 'Contact', cell: (organisation) => organisation.contact_name },
  { header: 'Email', cell: (organisation) => organisation.contact_email },
  { header: 'Phone', cell: (organisation) => organisation.contact_phone ?? 'Not given' },
]

/**
 * The client organisations in the order the backend sent them. The ID leads, because it is what
 * staff give an organisation's Event Organisers to sign up with.
 */
export function OrganisationTable({ organisations }: { organisations: ClientOrganisation[] }) {
  if (organisations.length === 0) {
    return <EmptyState message="No client organisations yet." />
  }
  return (
    <DataTable
      caption="Client organisations"
      columns={COLUMNS}
      rows={organisations}
      getRowKey={(organisation) => organisation.id}
    />
  )
}
