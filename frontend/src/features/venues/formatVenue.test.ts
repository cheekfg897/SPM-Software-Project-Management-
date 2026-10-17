import { VENUE_LAYOUTS } from '@/config/venueLayouts'
import type { VenueLayout } from '@/config/venueLayouts'

import { WEEKDAYS } from './constants'
import type { Weekday } from './constants'
import {
  formatClock,
  formatMinutes,
  formatPeriodHours,
  layoutLabel,
  weekdayLabel,
} from './formatVenue'

describe('SCRUM-25 how a venue reads on screen', () => {
  it.each([
    ['00:00', '12:00 am'],
    ['09:05', '9:05 am'],
    ['12:00', '12:00 pm'],
    ['18:30', '6:30 pm'],
    ['23:59', '11:59 pm'],
  ])('writes the 24-hour time %s as %s, whatever the time zone', (time, expected) => {
    expect(formatClock(time)).toBe(expected)
  })

  it('writes a same-day period as its two times', () => {
    const period = {
      open: { day: 'tuesday', time: '08:00' },
      close: { day: 'tuesday', time: '22:00' },
    } as const

    expect(formatPeriodHours(period)).toBe('8:00 am – 10:00 pm')
  })

  it('names the day a period closes on when it runs past midnight', () => {
    const period = {
      open: { day: 'saturday', time: '18:00' },
      close: { day: 'sunday', time: '02:00' },
    } as const

    expect(formatPeriodHours(period)).toBe('6:00 pm – Sunday 2:00 am')
  })

  it('names every weekday and layout the backend sends', () => {
    expect(WEEKDAYS.map(({ value }) => weekdayLabel(value))).toEqual([
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ])
    expect(VENUE_LAYOUTS.map(({ value }) => layoutLabel(value))).toEqual([
      'Classroom',
      'Theatre',
      'Boardroom',
      'Banquet',
      'Exhibition',
      'Other',
    ])
  })

  it('shows a day or layout the web app does not know yet as the backend wrote it', () => {
    // As if the backend had added a value since: the types can't hold it, so it is cast here.
    expect(weekdayLabel('holiday' as Weekday)).toBe('holiday')
    expect(layoutLabel('cabaret' as VenueLayout)).toBe('cabaret')
  })

  it.each([
    [0, 'None'],
    [1, '1 minute'],
    [45, '45 minutes'],
  ])('writes %i minutes as "%s"', (minutes, expected) => {
    expect(formatMinutes(minutes)).toBe(expected)
  })
})
