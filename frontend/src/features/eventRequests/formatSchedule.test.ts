import { formatSchedule } from './formatSchedule'

describe('SCRUM-24 formatSchedule', () => {
  it('gives the day and the times of an event on one day', () => {
    const schedule = {
      proposed_date: '2026-11-12',
      end_date: '2026-11-12',
      start_time: '09:00:00',
      end_time: '17:30:00',
    }

    expect(formatSchedule(schedule)).toBe('Thu, 12 Nov · 9:00 am – 5:30 pm')
  })

  it('names both days of an event that ends on a later day', () => {
    const schedule = {
      proposed_date: '2026-12-03',
      end_date: '2026-12-04',
      start_time: '10:00:00',
      end_time: '16:00:00',
    }

    expect(formatSchedule(schedule)).toBe('Thu, 3 Dec, 10:00 am – Fri, 4 Dec, 4:00 pm')
  })

  it('reads the date as written, wherever the viewer is', () => {
    // A date has no time zone: 12 Nov is 12 Nov even where it is still 11 Nov in UTC.
    const schedule = {
      proposed_date: '2026-11-12',
      end_date: null,
      start_time: '00:00:00',
      end_time: '00:30:00',
    }

    expect(formatSchedule(schedule)).toBe('Thu, 12 Nov · 12:00 am – 12:30 am')
  })

  it('gives only the day of a draft whose times are not set yet', () => {
    const schedule = {
      proposed_date: '2026-11-12',
      end_date: null,
      start_time: null,
      end_time: null,
    }

    expect(formatSchedule(schedule)).toBe('Thu, 12 Nov')
  })

  it('says the date is still to be set on a draft without one', () => {
    const schedule = { proposed_date: null, end_date: null, start_time: null, end_time: null }

    expect(formatSchedule(schedule)).toBe('Date to be set')
  })
})
