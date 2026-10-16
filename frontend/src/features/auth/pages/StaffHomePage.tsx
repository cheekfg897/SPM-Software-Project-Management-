import type { ReactNode } from 'react'

import { PageContainer } from '@/components/layout'

import { Greeting } from '../components/Greeting'

/**
 * The landing view for every staff role (SCRUM-6 AC3): a greeting, then what the route table
 * puts inside it (a coordinator's assigned events), so this feature needn't import another's.
 */
export function StaffHomePage({ children }: { children: ReactNode }) {
  return (
    <PageContainer title="Staff home" description="The events and requests you look after.">
      <Greeting />
      {children}
    </PageContainer>
  )
}
