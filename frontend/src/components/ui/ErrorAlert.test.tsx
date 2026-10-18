import { render, screen, within } from '@testing-library/react'

import { ApiError } from '@/lib/api'

import { ErrorAlert, RefusalAlert } from './ErrorAlert'

describe('ErrorAlert', () => {
  it("shows the backend's message", () => {
    render(<ErrorAlert error={new ApiError(409, 'conflict', 'Email already registered.')} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Email already registered.')
  })

  it('shows a generic message for an error that did not come from the backend', () => {
    render(<ErrorAlert error={new TypeError('x is undefined')} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong. Please try again.')
  })

  it('shows nothing when there is no error', () => {
    const { container } = render(<ErrorAlert error={null} />)

    expect(container).toBeEmptyDOMElement()
  })
})

describe('RefusalAlert', () => {
  /** A refusal whose details are reasons, as the backend sends a gate's gaps (ADR-0051). */
  const GAPS = new ApiError(409, 'confirmation_not_allowed', 'Not ready, says the backend.', {
    safety_check: ['The Safety Officer has not approved the event.'],
    venue_arrangements: ['Venue arrangement 12 is pending.', 'Venue arrangement 14 is rejected.'],
  })

  it("lists every message in the details under the backend's message, in its order", () => {
    render(<RefusalAlert error={GAPS} />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Not ready, says the backend.')
    const reasons = within(alert).getAllByRole('listitem')
    expect(reasons.map((reason) => reason.textContent)).toEqual([
      'The Safety Officer has not approved the event.',
      'Venue arrangement 12 is pending.',
      'Venue arrangement 14 is rejected.',
    ])
  })

  it('differs from ErrorAlert, which leaves the same details to the form, under its fields', () => {
    render(<ErrorAlert error={GAPS} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Not ready, says the backend.')
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows nothing when there is no error', () => {
    const { container } = render(<RefusalAlert error={null} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('draws no list for a refusal with no details', () => {
    render(<RefusalAlert error={new ApiError(409, 'conflict', 'Already done.')} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Already done.')
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })
})
