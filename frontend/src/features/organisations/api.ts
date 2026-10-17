import { apiRequest } from '@/lib/api'

/** The organisations module's endpoints (SCRUM-66). Staff only. */
const ORGANISATION_PATHS = {
  ORGANISATIONS: '/api/organisations',
} as const

/** A client organisation as the backend shows it to staff. */
export interface ClientOrganisation {
  id: number
  name: string
  contact_name: string
  contact_email: string
  contact_phone: string | null
  created_at: string | null
}

/** What the backend accepts when staff record an organisation. */
export interface NewClientOrganisation {
  name: string
  contact_name: string
  contact_email: string
  /** Optional; left out when not given. */
  contact_phone?: string
}

/** The list comes wrapped, as `{"organisations": [...]}`. */
interface OrganisationList {
  organisations: ClientOrganisation[]
}

export const organisationKeys = {
  all: ['organisations'] as const,
  list: () => [...organisationKeys.all, 'list'] as const,
}

/** Every client organisation, in the backend's order: by name. */
export async function fetchOrganisations(): Promise<ClientOrganisation[]> {
  const body = await apiRequest<OrganisationList>(ORGANISATION_PATHS.ORGANISATIONS)
  return body.organisations
}

export function createOrganisation(
  organisation: NewClientOrganisation,
): Promise<ClientOrganisation> {
  return apiRequest<ClientOrganisation>(ORGANISATION_PATHS.ORGANISATIONS, {
    method: 'POST',
    body: organisation,
  })
}
