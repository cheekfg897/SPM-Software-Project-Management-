import { render, screen } from '@testing-library/react'

import { Badge } from './Badge'

describe('SCRUM-28 Badge', () => {
  it('shows its text', () => {
    render(<Badge>Unread</Badge>)

    expect(screen.getByText('Unread')).toBeVisible()
  })

  it('is read out as its label, not its visible text, when it has one', () => {
    render(<Badge label="3 unread notifications">3</Badge>)

    expect(screen.getByText('3 unread notifications')).toBeInTheDocument()
    expect(screen.getByText('3')).toHaveAttribute('aria-hidden', 'true')
  })
})
