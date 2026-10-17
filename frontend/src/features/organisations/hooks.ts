import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { createOrganisation, fetchOrganisations, organisationKeys } from './api'
import type { NewClientOrganisation } from './api'

/** Every client organisation, by name (SCRUM-66). Staff only. */
export function useOrganisations() {
  return useQuery({ queryKey: organisationKeys.list(), queryFn: fetchOrganisations })
}

/** Record an organisation. Afterwards the list is read again, so it shows the backend's order. */
export function useCreateOrganisation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (organisation: NewClientOrganisation) => createOrganisation(organisation),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: organisationKeys.list() }),
  })
}
