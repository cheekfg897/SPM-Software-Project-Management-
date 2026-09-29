import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { SegmentedControl } from './SegmentedControl'

const OPTIONS = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
]

describe('SegmentedControl', () => {
  it('is a labelled group of radios with the current value checked', () => {
    render(<SegmentedControl label="Range" options={OPTIONS} value="week" onChange={vi.fn()} />)

    expect(screen.getByRole('radiogroup', { name: 'Range' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Week' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Day' })).not.toBeChecked()
  })

  it('reports the option chosen', async () => {
    const onChange = vi.fn()
    render(<SegmentedControl label="Range" options={OPTIONS} value="week" onChange={onChange} />)

    await userEvent.click(screen.getByRole('radio', { name: 'Day' }))

    expect(onChange).toHaveBeenCalledWith('day')
  })
})
