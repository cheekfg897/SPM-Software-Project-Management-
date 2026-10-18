import { attributed } from './attributed'

describe('attributed', () => {
  it('names who did it and when, in Singapore time', () => {
    expect(attributed('Reviewed', 'Tariq Hassan', '2026-10-05T17:30:00Z')).toBe(
      'Reviewed by Tariq Hassan, 6 Oct, 1:30 am',
    )
  })

  it('says only when for someone whose account is gone', () => {
    expect(attributed('Decided', null, '2026-10-05T09:00:00+08:00')).toBe('Decided 5 Oct, 9:00 am')
  })
})
