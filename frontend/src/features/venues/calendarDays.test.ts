import type { CalendarEntry } from './api'
import { addDays, calendarDays, rangeQuery, weekFrom } from './calendarDays'

function entry(start_time: string, end_time: string, reason: string): CalendarEntry {
  return { start_time, end_time, event_start: null, event_end: null, kind: 'block', reason }
}

describe('SCRUM-26 the days a venue calendar shows', () => {
  it.each([
    ['2026-11-10', 1, '2026-11-11'],
    ['2026-11-30', 1, '2026-12-01'],
    ['2026-12-31', 1, '2027-01-01'],
    ['2028-02-28', 1, '2028-02-29'],
    ['2026-11-10', 6, '2026-11-16'],
  ])('moves %s on by %i day(s) to %s', (date, days, expected) => {
    expect(addDays(date, days)).toBe(expected)
  })

  it('leaves a date it cannot read as it is, so the backend refuses it rather than the page breaking', () => {
    expect(addDays('2026-11-1x', 1)).toBe('2026-11-1x')
    expect(rangeQuery({ from: '2026-11-10', to: 'soon' })).toEqual({
      range_start: '2026-11-10T00:00:00',
      range_end: 'soonT00:00:00',
    })
  })

  it('opens on the week from today: today and the six days after', () => {
    expect(weekFrom('2026-11-28')).toEqual({ from: '2026-11-28', to: '2026-12-04' })
  })

  it('asks for whole days: from the first midnight to the midnight after the last day', () => {
    expect(rangeQuery({ from: '2026-11-10', to: '2026-11-12' })).toEqual({
      range_start: '2026-11-10T00:00:00',
      range_end: '2026-11-13T00:00:00',
    })
  })

  it('lists every day of the range, each with the periods touching it, in the order sent', () => {
    const lateBlock = entry('2026-11-10T18:00:00+08:00', '2026-11-10T20:00:00+08:00', 'late')
    const earlyBlock = entry('2026-11-10T08:00:00+08:00', '2026-11-10T09:00:00+08:00', 'early')
    const overnight = entry('2026-11-10T22:00:00+08:00', '2026-11-11T02:00:00+08:00', 'overnight')

    const days = calendarDays({ from: '2026-11-10', to: '2026-11-12' }, [
      lateBlock,
      earlyBlock,
      overnight,
    ])

    expect(days).toEqual([
      { day: '2026-11-10', entries: [lateBlock, earlyBlock, overnight] },
      { day: '2026-11-11', entries: [overnight] },
      { day: '2026-11-12', entries: [] },
    ])
  })

  it('puts a period that ends at midnight on its own day only, and one that starts there on the next', () => {
    const endsAtMidnight = entry('2026-11-10T20:00:00+08:00', '2026-11-11T00:00:00+08:00', 'a')
    const startsAtMidnight = entry('2026-11-11T00:00:00+08:00', '2026-11-11T01:00:00+08:00', 'b')

    const days = calendarDays({ from: '2026-11-10', to: '2026-11-11' }, [
      endsAtMidnight,
      startsAtMidnight,
    ])

    expect(days).toEqual([
      { day: '2026-11-10', entries: [endsAtMidnight] },
      { day: '2026-11-11', entries: [startsAtMidnight] },
    ])
  })

  it('reads days in business time, whatever offset a time is written with', () => {
    const lateUtc = entry('2026-11-10T17:00:00Z', '2026-11-10T17:30:00Z', 'utc')

    const days = calendarDays({ from: '2026-11-10', to: '2026-11-11' }, [lateUtc])

    expect(days.map(({ entries }) => entries.length)).toEqual([0, 1])
  })

  it('shows no days for a range that ends before it starts', () => {
    expect(calendarDays({ from: '2026-11-12', to: '2026-11-10' }, [])).toEqual([])
  })
})
