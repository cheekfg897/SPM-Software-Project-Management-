import { render, screen } from '@testing-library/react'

import { Field } from './Field'

function renderField(props: { errors?: string[]; hint?: string } = {}) {
  render(
    <Field label="Venue" {...props}>
      {(control) => <input {...control} />}
    </Field>,
  )
  return screen.getByLabelText('Venue')
}

describe('Field', () => {
  it('labels the control it draws', () => {
    const control = renderField()

    expect(control).toHaveAttribute('aria-invalid', 'false')
    expect(control).not.toHaveAttribute('aria-describedby')
  })

  it('lists the errors, describes the control by them and marks it invalid', () => {
    const control = renderField({ errors: ['Too short.', 'No digit.'], hint: 'Ignored.' })

    expect(control).toHaveAttribute('aria-invalid', 'true')
    expect(control).toHaveAccessibleDescription('Too short. No digit.')
  })

  it('describes the control by its hint while there are no errors', () => {
    const control = renderField({ hint: 'Ask Venue Staff.' })

    expect(control).toHaveAccessibleDescription('Ask Venue Staff.')
    expect(control).toHaveAttribute('aria-invalid', 'false')
  })

  it('puts its class name on the wrapper', () => {
    render(
      <Field label="Venue" className="wide">
        {(control) => <input {...control} />}
      </Field>,
    )

    expect(screen.getByLabelText('Venue').parentElement).toHaveClass('wide')
  })
})
