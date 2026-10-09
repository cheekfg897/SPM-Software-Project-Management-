import type { ReactNode } from 'react'

import { PageContainer } from '@/components/layout'

import { Greeting } from '../components/Greeting'

/**
 * The Event Organiser's landing view (SCRUM-6 AC3): a greeting, then what the route table puts
 * inside it (their event requests), so this feature needn't import another's.
 */
export function OrganiserHomePage({ children }: { children: ReactNode }) {
  return (
    <PageContainer
      title="Your events"
      description="Every event request from your organisation, newest first."
    >
      <Greeting />
      {children}
    </PageContainer>
  )
}
