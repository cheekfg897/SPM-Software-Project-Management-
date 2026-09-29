import { isRecord } from './isRecord'

describe('isRecord', () => {
  it('accepts a plain object', () => {
    expect(isRecord({ a: 1 })).toBe(true)
  })

  it.each([null, undefined, [1], 'text', 3])('rejects %j', (value) => {
    expect(isRecord(value)).toBe(false)
  })
})
