import { PageContainer } from '@/components/layout'
import { ButtonLink } from '@/components/ui'
import { ROLE } from '@/config/roles'
import { eventEquipmentPath } from '@/config/routes'
import { selectSessionUser, useAppSelector } from '@/store'

import type { StaffEventRecord } from '../api'

import { AboutTheEvent } from './AboutTheEvent'
import { ClarificationList } from './ClarificationList'
import { CoordinatorDetails } from './CoordinatorDetails'
import { DecisionDetails } from './DecisionDetails'
import { EquipmentOnRecord } from './EquipmentOnRecord'
import { EventHistorySection } from './EventHistorySection'
import { RecordHeading } from './RecordHeading'
import { RecordSection } from './RecordSection'
import { SafetyOutcomeDetails } from './SafetyOutcomeDetails'
import { VenueArrangementList } from './VenueArrangementList'

const NO_INTERNAL_NOTES = 'No internal planning notes yet.'

/**
 * Any submitted event's record, read-only, for Venue Staff, Technical Support, the Safety Officer
 * and the Event Coordinator Lead (SCRUM-24 AC9, AC10; ADR-0095): its details and notes, its
 * coordinator, decision and clarifications, its venue arrangements and equipment with their
 * preparation (SCRUM-84 AC2, SCRUM-85 AC2), its safety outcome and its history (SCRUM-33 AC5).
 * Nothing on it changes the event, and it has no registrants (SCRUM-55). Technical Support also
 * get a link to the event's Equipment page, where they reserve and prepare its equipment.
 */
export function StaffEventRecordView({ record }: { record: StaffEventRecord }) {
  const viewer = useAppSelector(selectSessionUser)
  const isTechnicalSupport = viewer?.role === ROLE.TECHNICAL_SUPPORT_STAFF
  return (
    <PageContainer title={record.name}>
      <RecordHeading request={record} />
      {isTechnicalSupport && (
        <div className="mt-8">
          <ButtonLink to={eventEquipmentPath(record.reference)} variant="secondary">
            Equipment
          </ButtonLink>
        </div>
      )}

      <RecordSection title="About the event">
        <AboutTheEvent record={record} />
      </RecordSection>
      <RecordSection title="Coordinator">
        <CoordinatorDetails coordinator={record.coordinator} />
      </RecordSection>
      {record.decision !== null && (
        <RecordSection title="Decision">
          <DecisionDetails decision={record.decision} />
        </RecordSection>
      )}
      {record.clarifications.length > 0 && (
        <RecordSection title="Clarifications">
          <ClarificationList clarifications={record.clarifications} />
        </RecordSection>
      )}
      {record.programme_notes !== null && (
        <RecordSection title="Programme notes">
          <p className="text-ink whitespace-pre-line">{record.programme_notes}</p>
        </RecordSection>
      )}
      <RecordSection title="Internal planning notes">
        {record.internal_planning_notes === null ? (
          <p className="text-ink-muted">{NO_INTERNAL_NOTES}</p>
        ) : (
          <p className="text-ink whitespace-pre-line">{record.internal_planning_notes}</p>
        )}
      </RecordSection>
      <RecordSection title="Venue arrangements">
        <VenueArrangementList arrangements={record.venue_arrangements} />
      </RecordSection>
      <RecordSection title="Equipment">
        <EquipmentOnRecord
          lines={record.equipment_lines}
          reservations={record.equipment_reservations}
        />
      </RecordSection>
      <RecordSection title="Safety check">
        <SafetyOutcomeDetails outcome={record.safety_outcome} />
      </RecordSection>
      <EventHistorySection reference={record.reference} />
    </PageContainer>
  )
}
