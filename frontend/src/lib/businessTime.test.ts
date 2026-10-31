import { toBusinessTimeIso, toTimeInputValue } from './businessTime'

describe('toBusinessTimeIso', () => {
  it('turns what a date-time input holds into an ISO date-time in business time', () => {
    expect(toBusinessTimeIso('2026-11-10T09:30')).toBe('2026-11-10T09:30:00+08:00')
  })
})

describe('toTimeInputValue', () => {
  it('turns a saved time of day into what a time input holds, to the minute', () => {
    expect(toTimeInputValue('19:30:00')).toBe('19:30')
  })
})
