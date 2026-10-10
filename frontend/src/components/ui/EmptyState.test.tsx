import { render, screen } from '@testing-library/react'

import { EmptyState } from './EmptyState'

describe('SCRUM-28 EmptyState', () => {
  it('shows the message and anything placed under it', () => {
    render(
      <EmptyState message="Nothing here yet.">
        <button type="button">Start</button>
      </EmptyState>,
    )

    expect(screen.getByText('Nothing here yet.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Start' })).toBeVisible()
  })
})
