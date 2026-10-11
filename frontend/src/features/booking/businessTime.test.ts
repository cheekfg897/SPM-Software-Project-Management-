import { toBusinessTimeIso } from './businessTime'

describe('SCRUM-42 toBusinessTimeIso', () => {
  it('turns what a date-time input holds into an ISO date-time in business time', () => {
    expect(toBusinessTimeIso('2026-11-10T09:30')).toBe('2026-11-10T09:30:00+08:00')
  })
})
