import { render, screen } from '@testing-library/react'

import { Badge } from './Badge'

describe('SCRUM-28 Badge', () => {
  it('shows its text', () => {
    render(<Badge>Unread</Badge>)

    expect(screen.getByText('Unread')).toBeVisible()
  })
})
