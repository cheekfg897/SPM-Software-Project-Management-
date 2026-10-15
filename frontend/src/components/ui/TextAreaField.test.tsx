import { render, screen } from '@testing-library/react'

import { TextAreaField } from './TextAreaField'

describe('TextAreaField', () => {
  it('labels its text area', () => {
    render(<TextAreaField label="Description" name="description" />)

    const textArea = screen.getByLabelText('Description')
    expect(textArea.tagName).toBe('TEXTAREA')
    expect(textArea).toHaveAttribute('name', 'description')
  })

  it('shows the backend messages for its field and marks the text area invalid', () => {
    render(<TextAreaField label="Purpose" name="purpose" errors={['Too long.']} />)

    const textArea = screen.getByLabelText('Purpose')
    expect(textArea).toHaveAttribute('aria-invalid', 'true')
    expect(textArea).toHaveAccessibleDescription('Too long.')
  })

  it('shows a hint when there are no errors', () => {
    render(
      <TextAreaField label="Accessibility needs" name="accessibility_needs" hint="Optional." />,
    )

    expect(screen.getByLabelText('Accessibility needs')).toHaveAccessibleDescription('Optional.')
    expect(screen.getByLabelText('Accessibility needs')).toHaveAttribute('aria-invalid', 'false')
  })
})
