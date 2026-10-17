import { PageContainer } from '@/components/layout'
import { ButtonLink, StatusChip } from '@/components/ui'
import { ROLE } from '@/config/roles'
import { eventEquipmentPath, venueRequestsPath } from '@/config/routes'
import { formatDateTime } from '@/lib/formatDate'
import { selectSessionUser, useAppSelector } from '@/store'

import type { Clarification, CoordinatorContact, Decision, EventRecord } from '../api'
import { formatSchedule } from '../formatSchedule'

import { RecordSection } from './RecordSection'

interface DecisionStyle {
  label: string
  /** Theme-token class for the outcome's colour. */
  tone: string
}

const DECISION_STYLE: Record<Decision['outcome'], DecisionStyle> = {
  approved: { label: 'Approved', tone: 'text-success' },
  rejected: { label: 'Rejected', tone: 'text-danger' },
}

/**
 * e.g. "Decided by Marcus Tan, 29 Sept, 3:20 pm". The backend sends no name for someone whose
 * account is gone (events/services.py `_actor_name`), and then it's only when.
 */
function attributed(action: string, name: string | null, at: string): string {
  const when = formatDateTime(at)
  if (name === null) {
    return `${action} ${when}`
  }
  return `${action} by ${name}, ${when}`
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

/** Where the event's assigned coordinator plans it next. Only they may open these pages. */
function CoordinatorLinks({ reference }: { reference: string }) {
  const viewer = useAppSelector(selectSessionUser)
  if (viewer?.role !== ROLE.EVENT_COORDINATOR) {
    return null
  }
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
 * ADR-0056). Which record a viewer may open is the backend's call.
 */
export function EventRecordView({ record }: { record: EventRecord }) {
  return (
    <PageContainer title={record.name}>
      <p className="text-flare mt-3 font-medium">{formatSchedule(record)}</p>
      <div className="mt-3 flex items-center gap-3">
        <StatusChip status={record.status} />
        <span className="text-ink-muted text-sm">{record.reference}</span>
      </div>
      <CoordinatorLinks reference={record.reference} />

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
        </RecordSection>
      )}
      {record.programme_notes !== null && (
        <RecordSection title="Programme notes">
          <p className="text-ink whitespace-pre-line">{record.programme_notes}</p>
        </RecordSection>
      )}
    </PageContainer>
  )
}
