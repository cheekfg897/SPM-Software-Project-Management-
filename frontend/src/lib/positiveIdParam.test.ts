import { positiveIdParam } from './positiveIdParam'

describe('positiveIdParam', () => {
  it('reads an id from the URL parameter it is named by', () => {
    expect(positiveIdParam(new URLSearchParams('venue=32&replaces=9104'), 'replaces')).toBe(9104)
  })

  it('reads no id when the parameter is missing', () => {
    expect(positiveIdParam(new URLSearchParams('venue=32'), 'replaces')).toBeNull()
  })

  it.each(['abc', '0', '-3', '2.5', ''])('reads no id from %j', (value) => {
    expect(positiveIdParam(new URLSearchParams({ replaces: value }), 'replaces')).toBeNull()
  })
})
