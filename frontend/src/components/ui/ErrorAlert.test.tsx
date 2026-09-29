import { render, screen } from '@testing-library/react'

import { ApiError } from '@/lib/api'

import { ErrorAlert } from './ErrorAlert'

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
