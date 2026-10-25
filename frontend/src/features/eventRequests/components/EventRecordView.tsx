import { PageContainer } from '@/components/layout'
import { ButtonLink } from '@/components/ui'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import { eventEquipmentPath, venueRequestsPath } from '@/config/routes'
import { selectSessionUser, useAppSelector } from '@/store'

import { isOrganiserEquipmentLine } from '../api'
import type { EventRecord } from '../api'
import { useAnswerClarification } from '../hooks'

import { AboutTheEvent } from './AboutTheEvent'
import { ClarificationList } from './ClarificationList'
import { CoordinatorDetails } from './CoordinatorDetails'
import { DecisionDetails } from './DecisionDetails'
import { EditDetailsSection } from './EditDetailsSection'
import { EventHistorySection } from './EventHistorySection'
import { MessageForm } from './MessageForm'
import { OrganiserEquipment } from './OrganiserEquipment'
import { OrganiserVenues } from './OrganiserVenues'
import { RecordActions } from './RecordActions'
import { RecordHeading } from './RecordHeading'
import { RecordSection } from './RecordSection'
import { RegistrantsSection } from './RegistrantsSection'
import { ReviewActions } from './ReviewActions'
import { SafetyDecisionDetails } from './SafetyDecisionDetails'

/** The organiser's answer to the open question (SCRUM-32 AC2, ADR-0060). */
function AnswerClarification({ reference }: { reference: string }) {
  const answer = useAnswerClarification(reference)
  return (
    <div className="mt-4">
      <MessageForm
        label="Your answer"
        field="response"
        submitLabel="Send answer"
        mutation={answer}
      />
    </div>
  )
}

/** Where the event's assigned coordinator plans it next. Only they may open these pages. */
function CoordinatorLinks({ reference }: { reference: string }) {
  return (
    <div className="mt-8 flex flex-wrap gap-3">
      <ButtonLink to={venueRequestsPath(reference)} variant="secondary">
        Venue requests
      </ButtonLink>
      <ButtonLink to={eventEquipmentPath(reference)} variant="secondary">
        Equipment
      </ButtonLink>
    </div>
  )
}

/**
 * An event request's record, with the sections the backend sent: its details, its coordinator,
 * and its decision, clarifications and programme notes once there are any (SCRUM-24 AC9,
 * ADR-0056). Which record a viewer may open is the backend's call. Its assigned coordinator
 * also gets links on and the review actions, and an organiser answers an open question here
 * (SCRUM-31, SCRUM-32, ADR-0060) and sees their equipment (SCRUM-37 AC5, ADR-0098) and, once
 * the event is confirmed, its venues and the Safety Officer's final decision (SCRUM-49 AC11,
 * ADR-0099).
 */
export function EventRecordView({ record }: { record: EventRecord }) {
  const viewer = useAppSelector(selectSessionUser)
  const isCoordinator = viewer?.role === ROLE.EVENT_COORDINATOR
  const isAnswerNeeded =
    viewer?.role === ROLE.EVENT_ORGANISER &&
    record.status === EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION
  // Only the organiser's record names each line's equipment; the coordinator works on the
  // lines from the Equipment page instead.
  const organisersEquipment = record.equipment_lines.filter(isOrganiserEquipmentLine)
  // Only the organiser's record lists the venues and the safety decision, and only once the
  // event is confirmed.
  const confirmedVenues = record.venue_arrangements ?? []
  const safetyDecision = record.safety_decision ?? null
  return (
    <PageContainer title={record.name}>
      <RecordHeading request={record} />
      {isCoordinator && <CoordinatorLinks reference={record.reference} />}
      {isCoordinator && <ReviewActions request={record} />}
      {isCoordinator && <RecordActions record={record} />}

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
          {isAnswerNeeded && <AnswerClarification reference={record.reference} />}
        </RecordSection>
      )}
      {safetyDecision !== null && (
        <RecordSection title="Safety check">
          <SafetyDecisionDetails decision={safetyDecision} />
        </RecordSection>
      )}
      {confirmedVenues.length > 0 && (
        <RecordSection title="Venues">
          <OrganiserVenues arrangements={confirmedVenues} />
        </RecordSection>
      )}
      {organisersEquipment.length > 0 && (
        <RecordSection title="Equipment">
          <OrganiserEquipment lines={organisersEquipment} />
        </RecordSection>
      )}
      {record.programme_notes !== null && (
        <RecordSection title="Programme notes">
          <p className="text-ink whitespace-pre-line">{record.programme_notes}</p>
        </RecordSection>
      )}
      {isCoordinator && <EditDetailsSection record={record} />}
      <EventHistorySection reference={record.reference} />
      <RegistrantsSection reference={record.reference} />
    </PageContainer>
  )
}
