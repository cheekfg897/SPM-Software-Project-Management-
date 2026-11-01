import { PageContainer } from '@/components/layout'
import { ButtonLink } from '@/components/ui'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import { eventEquipmentPath, venueRequestsPath } from '@/config/routes'
import { venueSearchForEventPath } from '@/features/venueSearch/searchParams'
import { selectSessionUser, useAppSelector } from '@/store'

import { isRecordEquipmentLine } from '../api'
import type { EventRecord } from '../api'
import { CHANGE_REQUESTABLE_STATUSES } from '../changeRequest'
import { useAnswerClarification } from '../hooks'

import { AboutTheEvent } from './AboutTheEvent'
import { ChangeRequestList } from './ChangeRequestList'
import { ClarificationList } from './ClarificationList'
import { CoordinatorDetails } from './CoordinatorDetails'
import { DecisionDetails } from './DecisionDetails'
import { EditDetailsSection } from './EditDetailsSection'
import { EquipmentOnRecord } from './EquipmentOnRecord'
import { EventHistorySection } from './EventHistorySection'
import { MessageForm } from './MessageForm'
import { PlanningNotes } from './PlanningNotes'
import { RecordActions } from './RecordActions'
import { RecordHeading } from './RecordHeading'
import { RecordSection } from './RecordSection'
import { RegistrantsSection } from './RegistrantsSection'
import { RequestChangeForm } from './RequestChangeForm'
import { ReviewActions } from './ReviewActions'
import { SafetyOutcomeDetails } from './SafetyOutcomeDetails'
import { VenueArrangementList } from './VenueArrangementList'

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

/**
 * Where the event's assigned coordinator plans it next. Only they may open these pages. Venue
 * search opens with the event's details filled in (SCRUM-90).
 */
function CoordinatorLinks({ reference }: { reference: string }) {
  return (
    <div className="mt-8 flex flex-wrap gap-3">
      <ButtonLink to={venueSearchForEventPath(reference)} variant="secondary">
        Find a venue for this event
      </ButtonLink>
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
 * (SCRUM-31, SCRUM-32, ADR-0060). The organiser is sent everything else on the record too, at
 * every stage: the planning notes, every venue arrangement, the equipment with its outcomes and
 * reservations, and the safety check (SCRUM-24 AC10, ADR-0104). Both see the organiser's change
 * requests, and the organiser raises and withdraws them here (SCRUM-56, ADR-0126).
 */
export function EventRecordView({ record }: { record: EventRecord }) {
  const viewer = useAppSelector(selectSessionUser)
  const isCoordinator = viewer?.role === ROLE.EVENT_COORDINATOR
  const isOrganiser = viewer?.role === ROLE.EVENT_ORGANISER
  const isAnswerNeeded =
    isOrganiser && record.status === EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION
  // Offered only in the statuses the backend takes a change request in (SCRUM-56 AC1, AC6).
  const isChangeRequestable = isOrganiser && CHANGE_REQUESTABLE_STATUSES.includes(record.status)
  // Only the organiser's record names each line's equipment and sends the rest of the record:
  // everything on it, at every stage (ADR-0104). The coordinator works on the lines and the
  // safety check from their own pages instead, and sees the venues listed here (ADR-0105).
  const recordLines = record.equipment_lines.filter(isRecordEquipmentLine)
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
      {record.programme_notes !== null && (
        <RecordSection title="Programme notes">
          <p className="text-ink whitespace-pre-line">{record.programme_notes}</p>
        </RecordSection>
      )}
      {record.internal_planning_notes !== undefined && (
        <RecordSection title="Planning notes">
          <PlanningNotes notes={record.internal_planning_notes} />
        </RecordSection>
      )}
      {record.venue_arrangements !== undefined && (
        <RecordSection title="Venue arrangements">
          <VenueArrangementList arrangements={record.venue_arrangements} />
        </RecordSection>
      )}
      {record.equipment_reservations !== undefined && (
        <RecordSection title="Equipment">
          <EquipmentOnRecord lines={recordLines} reservations={record.equipment_reservations} />
        </RecordSection>
      )}
      {record.safety_outcome !== undefined && (
        <RecordSection title="Safety check">
          <SafetyOutcomeDetails outcome={record.safety_outcome} />
        </RecordSection>
      )}
      {record.change_requests.length > 0 && (
        <RecordSection title="Change requests">
          <ChangeRequestList reference={record.reference} changeRequests={record.change_requests} />
        </RecordSection>
      )}
      {isChangeRequestable && (
        <RecordSection title="Request a change">
          <RequestChangeForm record={record} />
        </RecordSection>
      )}
      {isCoordinator && <EditDetailsSection record={record} />}
      <EventHistorySection reference={record.reference} />
      <RegistrantsSection reference={record.reference} />
    </PageContainer>
  )
}
