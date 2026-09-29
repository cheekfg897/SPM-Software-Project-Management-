import { formText } from './formText'

describe('formText', () => {
  it('reads a text field', () => {
    const form = new FormData()
    form.set('email', 'alice@example.com')

    expect(formText(form, 'email')).toBe('alice@example.com')
  })

  it('reads a missing or file field as empty', () => {
    const form = new FormData()
    form.set('avatar', new File(['x'], 'a.png'))

    expect(formText(form, 'email')).toBe('')
    expect(formText(form, 'avatar')).toBe('')
  })
})
