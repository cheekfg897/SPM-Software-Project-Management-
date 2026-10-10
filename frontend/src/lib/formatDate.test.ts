import {
  businessDate,
  formatDateTime,
  formatShortDate,
  formatTimeRange,
  formatWeekday,
} from './formatDate'

describe('SCRUM-52 formatDate', () => {
  it('reads the business date in Singapore, whatever offset the time was sent with', () => {
    expect(businessDate('2026-10-05T17:30:00Z')).toBe('2026-10-06')
    expect(businessDate('2026-10-05T19:30:00+08:00')).toBe('2026-10-05')
  })

  it('names the day and the date', () => {
    expect(formatWeekday('2026-10-05T19:30:00+08:00')).toBe('Monday')
    expect(formatShortDate('2026-10-05T19:30:00+08:00')).toBe('5 Oct')
  })

  it('gives the time range of an event that ends the same day', () => {
    expect(formatTimeRange('2026-10-05T19:30:00+08:00', '2026-10-05T22:00:00+08:00')).toBe(
      '7:30 pm – 10:00 pm',
    )
  })

  it('names the end day of an event that runs past midnight', () => {
    expect(formatTimeRange('2026-10-09T21:00:00+08:00', '2026-10-10T00:00:00+08:00')).toBe(
      '9:00 pm – Sat 12:00 am',
    )
  })

  it('gives the date and time in Singapore, whatever offset the time was sent with', () => {
    expect(formatDateTime('2026-10-05T09:00:00+08:00')).toBe('5 Oct, 9:00 am')
    expect(formatDateTime('2026-10-05T17:30:00Z')).toBe('6 Oct, 1:30 am')
  })
})
