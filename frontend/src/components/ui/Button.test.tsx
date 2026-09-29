import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import { Button, ButtonLink } from './Button'

describe('Button', () => {
  it('is a submit button only when asked to be', () => {
    render(<Button>Save</Button>)

    expect(screen.getByRole('button', { name: 'Save' })).toHaveAttribute('type', 'button')
  })

  it('is disabled and busy while pending', () => {
    render(
      <Button type="submit" isPending>
        Save
      </Button>,
    )

    const button = screen.getByRole('button', { name: 'Save' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })
})

describe('ButtonLink', () => {
  it('links to the page given', () => {
    render(
      <MemoryRouter>
        <ButtonLink to="/events" variant="secondary">
          Browse
        </ButtonLink>
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Browse' })).toHaveAttribute('href', '/events')
  })
})
