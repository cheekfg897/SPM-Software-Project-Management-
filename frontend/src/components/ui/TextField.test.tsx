import { render, screen } from '@testing-library/react'

import { TextField } from './TextField'

describe('TextField', () => {
  it('labels its input', () => {
    render(<TextField label="Email" name="email" type="email" />)

    expect(screen.getByLabelText('Email')).toHaveAttribute('name', 'email')
  })

  it('shows the backend messages for its field and marks the input invalid', () => {
    render(<TextField label="Password" name="password" errors={['Too short.', 'No digit.']} />)

    const input = screen.getByLabelText('Password')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription('Too short. No digit.')
  })

  it('shows a hint when there are no errors', () => {
    render(
      <TextField label="Organisation ID" name="organisation_id" hint="Ask your coordinator." />,
    )

    expect(screen.getByLabelText('Organisation ID')).toHaveAccessibleDescription(
      'Ask your coordinator.',
    )
    expect(screen.getByLabelText('Organisation ID')).toHaveAttribute('aria-invalid', 'false')
  })
})
