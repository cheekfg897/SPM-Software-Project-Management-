import { render, screen } from '@testing-library/react'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'

import { StatusChip } from './StatusChip'

/** What a user reads for each status, written out so a renamed label is noticed. */
const LABELS: [EventRequestStatus, string][] = [
  ['draft', 'Draft'],
  ['submitted', 'Submitted'],
  ['under_review', 'Under review'],
  ['awaiting_clarification', 'Awaiting clarification'],
  ['approved', 'Approved'],
  ['safety_review', 'Safety review'],
  ['confirmed', 'Confirmed'],
  ['completed', 'Completed'],
  ['cancelled', 'Cancelled'],
  ['rejected', 'Rejected'],
]

describe('SCRUM-24 StatusChip', () => {
  it('has a label for every status the backend can send', () => {
    const labelled = LABELS.map(([status]) => status)

    expect(labelled.sort()).toEqual(Object.values(EVENT_REQUEST_STATUS).sort())
  })

  it.each(LABELS)('shows %s as "%s"', (status, label) => {
    render(<StatusChip status={status} />)

    expect(screen.getByText(label)).toBeInTheDocument()
  })
})
