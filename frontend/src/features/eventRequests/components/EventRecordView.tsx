import { PageContainer } from '@/components/layout'
import { ButtonLink, StatusChip } from '@/components/ui'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import { eventEquipmentPath, venueRequestsPath } from '@/config/routes'
import { attributed } from '@/lib/attributed'
import { selectSessionUser, useAppSelector } from '@/store'

import { isOrganiserEquipmentLine } from '../api'
import type { Clarification, CoordinatorContact, Decision, EventRecord } from '../api'
import { formatSchedule } from '../formatSchedule'
import { useAnswerClarification } from '../hooks'

import { EditDetailsSection } from './EditDetailsSection'
import { EventHistorySection } from './EventHistorySection'
import { MessageForm } from './MessageForm'
import { OrganiserEquipment } from './OrganiserEquipment'
import { RecordActions } from './RecordActions'
import { RecordSection } from './RecordSection'
import { RegistrantsSection } from './RegistrantsSection'
import { ReviewActions } from './ReviewActions'

interface DecisionStyle {
  label: string
  /** Theme-token class for the outcome's colour. */
  tone: string
}

const DECISION_STYLE: Record<Decision['outcome'], DecisionStyle> = {
  approved: { label: 'Approved', tone: 'text-success' },
  rejected: { label: 'Rejected', tone: 'text-danger' },
}

/** The organiser's answers, each against its label, leaving out the ones not given. */
function detailsOf(record: EventRecord): [string, string][] {
  const details: [string, string][] = []
  if (record.expected_attendance !== null) {
    details.push(['Expected attendance', String(record.expected_attendance)])
  }
  const written: [string, string | null][] = [
    ['Purpose', record.purpose],
    ['Description', record.description],
    ['Venue requirements', record.venue_requirements],
    ['Accessibility needs', record.accessibility_needs],
    ['Equipment requirements', record.equipment_requirements],
  ]
  for (const [label, value] of written) {
    if (value !== null) {
      details.push([label, value])
    }
  }
  details.push(['Registration', record.registration_required ? 'Needed' : 'Not needed'])
  return details
}

function AboutTheEvent({ record }: { record: EventRecord }) {
  return (
    <dl className="border-line/60 bg-surface/50 divide-line/60 divide-y rounded-2xl border">
      {detailsOf(record).map(([label, value]) => (
        <div key={label} className="grid gap-1 px-5 py-4 sm:grid-cols-3 sm:gap-4">
          <dt className="text-ink-muted text-sm">{label}</dt>
          <dd className="text-ink whitespace-pre-line sm:col-span-2">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function CoordinatorDetails({ coordinator }: { coordinator: CoordinatorContact | null }) {
  if (coordinator === null) {
    return <p className="text-ink-muted">No coordinator is assigned yet.</p>
  }
  return (
    <p className="text-ink">
      {coordinator.full_name}
      <span className="text-ink-faint"> · </span>
      <a
        href={`mailto:${coordinator.email}`}
        className="text-flare hover:text-corona underline-offset-4 hover:underline"
      >
        {coordinator.email}
      </a>
    </p>
  )
}

function DecisionDetails({ decision }: { decision: Decision }) {
  const { label, tone } = DECISION_STYLE[decision.outcome]
  return (
    <div className="border-line/60 bg-surface/50 rounded-2xl border p-5">
      <p className={`font-semibold ${tone}`}>{label}</p>
      {decision.reason !== null && <p className="text-ink mt-2">{decision.reason}</p>}
      <p className="text-ink-faint mt-2 text-sm">
        {attributed('Decided', decision.decided_by, decision.decided_at)}
      </p>
    </div>
  )
}

/** One question, and the organiser's answer once they have given it. */
function ClarificationExchange({ clarification }: { clarification: Clarification }) {
  const { answered_at: answeredAt } = clarification
  return (
    <li className="border-line/60 bg-surface/50 rounded-2xl border p-5">
      <p className="text-ink">{clarification.message}</p>
      <p className="text-ink-faint mt-1 text-sm">
        {attributed('Asked', clarification.requested_by, clarification.requested_at)}
      </p>
      {answeredAt === null ? (
        <p className="text-flare mt-3 text-sm font-medium">Waiting for an answer.</p>
      ) : (
        <div className="border-line/60 mt-3 border-l-2 pl-4">
          <p className="text-ink">{clarification.response}</p>
          <p className="text-ink-faint mt-1 text-sm">
            {attributed('Answered', clarification.answered_by, answeredAt)}
          </p>
        </div>
      )}
    </li>
  )
}

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
 * (SCRUM-31, SCRUM-32, ADR-0060) and sees their equipment (SCRUM-37 AC5, ADR-0098).
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
  return (
    <PageContainer title={record.name}>
      <p className="text-flare mt-3 font-medium">{formatSchedule(record)}</p>
      <div className="mt-3 flex items-center gap-3">
        <StatusChip status={record.status} />
        <span className="text-ink-muted text-sm">{record.reference}</span>
      </div>
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
          <ol className="space-y-3">
            {record.clarifications.map((clarification) => (
              <ClarificationExchange
                key={clarification.requested_at}
                clarification={clarification}
              />
            ))}
          </ol>
          {isAnswerNeeded && <AnswerClarification reference={record.reference} />}
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
      {isCoordinator && <EditDetailsSection reference={record.reference} />}
      <EventHistorySection reference={record.reference} />
      <RegistrantsSection reference={record.reference} />
    </PageContainer>
  )
}
