import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { SelectField } from './SelectField'

const OPTIONS = [
  { value: 'theatre', label: 'Theatre' },
  { value: 'banquet', label: 'Banquet' },
]

describe('SelectField', () => {
  it('labels its select and offers an empty choice first, then the options', () => {
    render(<SelectField label="Layout" name="layout" options={OPTIONS} />)

    const select = screen.getByLabelText('Layout')
    expect(select).toHaveAttribute('name', 'layout')
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
      'No preference',
      'Theatre',
      'Banquet',
    ])
  })

  it('lets the user choose an option', async () => {
    render(<SelectField label="Layout" name="layout" options={OPTIONS} />)

    await userEvent.setup().selectOptions(screen.getByLabelText('Layout'), 'Banquet')

    expect(screen.getByLabelText('Layout')).toHaveValue('banquet')
  })

  it('shows the backend messages for its field and marks the select invalid', () => {
    render(<SelectField label="Layout" name="layout" options={OPTIONS} errors={['Not allowed.']} />)

    const select = screen.getByLabelText('Layout')
    expect(select).toHaveAttribute('aria-invalid', 'true')
    expect(select).toHaveAccessibleDescription('Not allowed.')
  })

  it('shows a hint under the select', () => {
    render(
      <SelectField label="Layout" name="layout" options={OPTIONS} hint="Leave empty if open." />,
    )

    expect(screen.getByLabelText('Layout')).toHaveAccessibleDescription('Leave empty if open.')
  })
})
