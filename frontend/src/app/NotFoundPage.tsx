import { PageContainer } from '@/components/layout'
import { ButtonLink } from '@/components/ui'
import { ROUTES } from '@/config/routes'

export function NotFoundPage() {
  return (
    <PageContainer title="Page not found" description="This page drifted past the event horizon.">
      <ButtonLink to={ROUTES.HOME} className="mt-8">
        Back to the start
      </ButtonLink>
    </PageContainer>
  )
}
