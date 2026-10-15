import { PageContainer } from '@/components/layout'
import { SegmentedControl } from '@/components/ui'
import type { SegmentedOption } from '@/components/ui'

import { MyEventsResults } from '../components/MyEventsResults'
import { MY_EVENTS_WHEN } from '../constants'
import type { MyEventsWhen } from '../constants'
import { useMyEventsWhen } from '../hooks'

const WHEN_OPTIONS: readonly SegmentedOption<MyEventsWhen>[] = [
  { value: MY_EVENTS_WHEN.UPCOMING, label: 'Upcoming' },
  { value: MY_EVENTS_WHEN.PAST, label: 'Past' },
]

/**
 * An Attendee's own events, upcoming or past (SCRUM-24 AC7, SCRUM-52 AC5, docs/adr/0044). The
 * backend splits and orders them; this page only shows the half the URL asks for.
 */
export function MyEventsPage() {
  const { when, choose } = useMyEventsWhen()

  return (
    <PageContainer title="My events" description="The events you have registered for.">
      <div className="mt-10">
        <SegmentedControl
          label="Which events"
          options={WHEN_OPTIONS}
          value={when}
          onChange={choose}
        />
      </div>
      <div className="mt-12">
        <MyEventsResults when={when} />
      </div>
    </PageContainer>
  )
}
