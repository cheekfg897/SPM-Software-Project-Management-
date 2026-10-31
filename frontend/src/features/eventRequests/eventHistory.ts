import { preparationStatusLabel } from '@/config/preparation'
import { formatDateTime, formatShortDate, formatTimeRange } from '@/lib/formatDate'
import { isRecord } from '@/lib/isRecord'

import type { EventHistoryEntry } from './api'
import { formatDay, formatTime } from './formatSchedule'
import { humanise } from './humanise'

/**
 * An event's history entries in plain English (SCRUM-33 AC4, AC5; ADR-0025, ADR-0076): what
 * happened, whether it was a significant change, and the facts its `details` hold, as label
 * and value pairs. The backend decides which entries a viewer sees; this only words them.
 */

/** Every kind of entry the backend writes (EventHistoryKind in events/models.py). */
export const EVENT_HISTORY_KIND = {
  COORDINATOR_ASSIGNED: 'coordinator_assigned',
  COORDINATOR_REASSIGNED: 'coordinator_reassigned',
  FIELD_CHANGED: 'field_changed',
  EVENT_COMPLETED: 'event_completed',
  REVIEW_STARTED: 'review_started',
  DECISION_RECORDED: 'decision_recorded',
  CLARIFICATION_REQUESTED: 'clarification_requested',
  CLARIFICATION_ANSWERED: 'clarification_answered',
  VENUE_BOOKING_REQUESTED: 'venue_booking_requested',
  VENUE_BOOKING_APPROVED: 'venue_booking_approved',
  VENUE_BOOKING_REJECTED: 'venue_booking_rejected',
  VENUE_BOOKING_RECONFIRMED: 'venue_booking_reconfirmed',
  VENUE_PREPARATION_UPDATED: 'venue_preparation_updated',
  EQUIPMENT_RESERVED: 'equipment_reserved',
  VENUE_ARRANGEMENT_CHANGED: 'venue_arrangement_changed',
  VENUE_ARRANGEMENT_WITHDRAWN: 'venue_arrangement_withdrawn',
  EQUIPMENT_OUTCOME_RECORDED: 'equipment_outcome_recorded',
  EQUIPMENT_PREPARATION_UPDATED: 'equipment_preparation_updated',
  SAFETY_REVIEW_REQUESTED: 'safety_review_requested',
  SAFETY_OUTCOME_RECORDED: 'safety_outcome_recorded',
  EVENT_CONFIRMED: 'event_confirmed',
} as const

export type EventHistoryKind = (typeof EVENT_HISTORY_KIND)[keyof typeof EVENT_HISTORY_KIND]

/** One thing an entry says, e.g. { label: 'Before', value: '250' }. */
export interface Fact {
  label: string
  value: string
}

export interface DescribedEntry {
  /** What happened, e.g. "Expected attendance changed". */
  title: string
  /** A change the backend marked significant (SCRUM-33 AC2). */
  isSignificant: boolean
  facts: Fact[]
}

type Details = Record<string, unknown>

/** How a value that was never set, or was cleared, is shown. */
const NOT_SET = 'Not set'
/** The fields whose values the backend stores as dates ("2026-11-12") or times ("09:00:00"). */
const DATE_FIELDS: readonly string[] = ['proposed_date', 'end_date']
const TIME_FIELDS: readonly string[] = ['start_time', 'end_time']
/** The fields the backend stores as instants and sends in business time (ADR-0086). */
const DATE_TIME_FIELDS: readonly string[] = ['withdrawal_cut_off']

/** `details[key]` if it is text; anything else, or nothing, is null. */
function textIn(details: Details, key: string): string | null {
  const value = details[key]
  return typeof value === 'string' ? value : null
}

/** `details[key]` as text if it is a number, such as an id or a quantity. */
function numberIn(details: Details, key: string): string | null {
  const value = details[key]
  return typeof value === 'number' ? String(value) : null
}

/** The facts that have a value, in the order given; one with none is left out. */
function factsOf(pairs: [string, string | null][]): Fact[] {
  const facts: Fact[] = []
  for (const [label, value] of pairs) {
    if (value !== null) {
      facts.push({ label, value })
    }
  }
  return facts
}

function entry(title: string, pairs: [string, string | null][] = []): DescribedEntry {
  return { title, isSignificant: false, facts: factsOf(pairs) }
}

/** A field's value as the record would show it: a day, a time, both, yes or no, or as written. */
function shownValue(field: string, value: unknown): string {
  if (value === null || value === undefined) {
    return NOT_SET
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }
  if (typeof value === 'string' && DATE_FIELDS.includes(field)) {
    return formatDay(value)
  }
  if (typeof value === 'string' && TIME_FIELDS.includes(field)) {
    return formatTime(value)
  }
  if (typeof value === 'string' && DATE_TIME_FIELDS.includes(field)) {
    return formatDateTime(value)
  }
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value)
  }
  return JSON.stringify(value)
}

/**
 * Fields whose name on screen isn't their key in words: the planning notes were once called
 * internal (SCRUM-33 AC1, ADR-0104), and the cut-off is written with its hyphen (SCRUM-69 AC7).
 */
const FIELD_LABELS: Partial<Record<string, string>> = {
  internal_planning_notes: 'Planning notes',
  withdrawal_cut_off: 'Withdrawal cut-off',
}

function fieldChanged(details: Details): DescribedEntry {
  const field = textIn(details, 'field')
  const label = field === null ? null : (FIELD_LABELS[field] ?? humanise(field))
  const title = label === null ? 'A detail changed' : `${label} changed`
  const name = field ?? ''
  return {
    ...entry(title, [
      ['Before', shownValue(name, details.previous_value)],
      ['After', shownValue(name, details.new_value)],
    ]),
    isSignificant: details.significant === true,
  }
}

function decisionRecorded(details: Details): DescribedEntry {
  const outcome = textIn(details, 'outcome')
  const title = outcome === null ? 'Decision recorded' : `Request ${outcome}`
  return entry(title, [['Reason', textIn(details, 'reason')]])
}

/**
 * e.g. "10 Nov, 9:00 am – 5:00 pm" for a venue's period, from the details' start and end keys:
 * the period asked for, or one a reconfirmation moved a booking from or to (SCRUM-59).
 */
function periodIn(details: Details, startKey: string, endKey: string): string | null {
  const startsAt = textIn(details, startKey)
  const endsAt = textIn(details, endKey)
  if (startsAt === null || endsAt === null) {
    return null
  }
  return `${formatShortDate(startsAt)}, ${formatTimeRange(startsAt, endsAt)}`
}

/** e.g. "80 → 120": a reconfirmed booking's expected occupancy before and after (SCRUM-59 AC10). */
function occupancyChange(details: Details): string | null {
  const before = numberIn(details, 'previous_expected_occupancy')
  const after = numberIn(details, 'expected_occupancy')
  if (before === null || after === null) {
    return null
  }
  return `${before} → ${after}`
}

function bookingReconfirmed(details: Details): DescribedEntry {
  return entry('Venue booking reconfirmed', [
    ['Venue ID', numberIn(details, 'venue_id')],
    ['Before', periodIn(details, 'previous_starts_at', 'previous_ends_at')],
    ['After', periodIn(details, 'starts_at', 'ends_at')],
    ['Expected occupancy', occupancyChange(details)],
    ['Reason', textIn(details, 'reason')],
  ])
}

/** Each field of an arrangement that changed, e.g. ["Expected occupancy", "80 → 120"]. */
function arrangementChanges(details: Details): [string, string][] {
  const changes = details.changes
  if (!isRecord(changes)) {
    return []
  }
  const pairs: [string, string][] = []
  for (const [field, change] of Object.entries(changes)) {
    if (isRecord(change)) {
      const from = shownValue(field, change.previous)
      const to = shownValue(field, change.new)
      pairs.push([humanise(field), `${from} → ${to}`])
    }
  }
  return pairs
}

function arrangementChanged(details: Details): DescribedEntry {
  return entry('Venue arrangement changed', [
    ['Venue ID', numberIn(details, 'venue_id')],
    ...arrangementChanges(details),
  ])
}

/** e.g. "2 of 4": how much of what was asked for Technical Support will provide. */
function providedOf(details: Details): string | null {
  const provided = numberIn(details, 'provided_quantity')
  const asked = numberIn(details, 'quantity')
  if (provided === null || asked === null) {
    return null
  }
  return `${provided} of ${asked}`
}

function equipmentOutcomeRecorded(details: Details): DescribedEntry {
  const status = textIn(details, 'status')
  return entry('Equipment review recorded', [
    ['Equipment', textIn(details, 'equipment_type_name')],
    ['Outcome', status === null ? null : humanise(status)],
    ['Provided', providedOf(details)],
    ['Note', textIn(details, 'note')],
  ])
}

/** The Safety Officer's note on each checklist item, in the order the backend sent them. */
function checklistNotes(details: Details): [string, string | null][] {
  const checklist = details.checklist
  if (!isRecord(checklist)) {
    return []
  }
  const pairs: [string, string | null][] = []
  for (const item of Object.keys(checklist)) {
    pairs.push([humanise(item), textIn(checklist, item)])
  }
  return pairs
}

function safetyOutcomeRecorded(details: Details): DescribedEntry {
  const outcome = textIn(details, 'outcome')
  return entry('Safety check recorded', [
    ['Outcome', outcome === null ? null : humanise(outcome)],
    ['Reason', textIn(details, 'reason')],
    ...checklistNotes(details),
  ])
}

/**
 * How each kind is worded. Typed over every kind, so a kind added to EVENT_HISTORY_KIND
 * without its wording here fails the typecheck.
 */
const DESCRIBE_KIND: Record<EventHistoryKind, (details: Details) => DescribedEntry> = {
  coordinator_assigned: (details) =>
    entry('Coordinator assigned', [['Coordinator', textIn(details, 'coordinator_name')]]),
  coordinator_reassigned: (details) =>
    entry('Coordinator changed', [
      ['From', textIn(details, 'previous_coordinator_name')],
      ['To', textIn(details, 'coordinator_name')],
    ]),
  field_changed: fieldChanged,
  event_completed: () => entry('Event marked completed'),
  review_started: () => entry('Review started'),
  decision_recorded: decisionRecorded,
  clarification_requested: (details) =>
    entry('Clarification requested', [['Question', textIn(details, 'message')]]),
  clarification_answered: (details) =>
    entry('Clarification answered', [['Answer', textIn(details, 'response')]]),
  venue_booking_requested: (details) =>
    entry('Venue booking requested', [
      ['Venue ID', numberIn(details, 'venue_id')],
      ['When', periodIn(details, 'starts_at', 'ends_at')],
    ]),
  venue_booking_approved: (details) =>
    entry('Venue booking approved', [
      ['Venue ID', numberIn(details, 'venue_id')],
      ['Reason', textIn(details, 'reason')],
    ]),
  venue_booking_rejected: (details) =>
    entry('Venue booking rejected', [
      ['Venue ID', numberIn(details, 'venue_id')],
      ['Reason', textIn(details, 'reason')],
    ]),
  venue_booking_reconfirmed: bookingReconfirmed,
  venue_preparation_updated: (details) =>
    entry('Venue preparation updated', [
      ['Venue ID', numberIn(details, 'venue_id')],
      ['Status', preparationStatusLabel(details.status)],
      ['Notes', textIn(details, 'notes')],
    ]),
  equipment_reserved: (details) =>
    entry('Equipment reserved', [
      ['Equipment', textIn(details, 'equipment_type_name')],
      ['Quantity', numberIn(details, 'quantity')],
    ]),
  venue_arrangement_changed: arrangementChanged,
  venue_arrangement_withdrawn: (details) =>
    entry('Venue arrangement withdrawn', [['Venue ID', numberIn(details, 'venue_id')]]),
  equipment_outcome_recorded: equipmentOutcomeRecorded,
  equipment_preparation_updated: (details) =>
    entry('Equipment preparation updated', [
      ['Equipment', textIn(details, 'equipment_type_name')],
      ['Status', preparationStatusLabel(details.status)],
      ['Notes', textIn(details, 'notes')],
    ]),
  safety_review_requested: () => entry('Sent for safety review'),
  safety_outcome_recorded: safetyOutcomeRecorded,
  event_confirmed: () => entry('Event confirmed'),
}

const KNOWN_KINDS: readonly string[] = Object.values(EVENT_HISTORY_KIND)

function isKnownKind(kind: string): kind is EventHistoryKind {
  return KNOWN_KINDS.includes(kind)
}

/**
 * What one entry says. A kind the backend added after this was written is named in words made
 * from the kind, with none of its details, so a new kind never breaks the page.
 */
export function describeHistoryEntry({
  kind,
  details,
}: Pick<EventHistoryEntry, 'kind' | 'details'>): DescribedEntry {
  if (!isKnownKind(kind)) {
    return entry(humanise(kind))
  }
  return DESCRIBE_KIND[kind](details)
}
