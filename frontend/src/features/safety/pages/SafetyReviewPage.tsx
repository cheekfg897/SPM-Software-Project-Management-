import { PageContainer } from '@/components/layout'

import { SafetyReviewList } from '../components/SafetyReviewList'

/** The Safety Officer's home: the events awaiting the safety check (SCRUM-97, SCRUM-98). */
export function SafetyReviewPage() {
  return (
    <PageContainer
      title="Safety review"
      description="Events whose venues and equipment are settled, soonest first. Check each one and record whether it is safe to go ahead: approve, reject or request changes."
    >
      <div className="mt-10">
        <SafetyReviewList />
      </div>
    </PageContainer>
  )
}
