import { groupByDay } from './groupByDay'

describe('SCRUM-52 groupByDay', () => {
  it('puts events on the same business day together, in the order given', () => {
    const late = { id: 1, starts_at: '2026-10-05T21:00:00+08:00' }
    const lateUtc = { id: 2, starts_at: '2026-10-05T14:30:00Z' } // 22:30 in Singapore, same day
    const nextDay = { id: 3, starts_at: '2026-10-06T09:00:00+08:00' }

    expect(groupByDay([late, lateUtc, nextDay])).toEqual([
      { day: '2026-10-05', events: [late, lateUtc] },
      { day: '2026-10-06', events: [nextDay] },
    ])
  })

  it('never reorders: a day that comes back later starts a new group', () => {
    const monday = { id: 1, starts_at: '2026-10-05T09:00:00+08:00' }
    const tuesday = { id: 2, starts_at: '2026-10-06T09:00:00+08:00' }
    const mondayAgain = { id: 3, starts_at: '2026-10-05T10:00:00+08:00' }

    expect(groupByDay([monday, tuesday, mondayAgain]).map((group) => group.day)).toEqual([
      '2026-10-05',
      '2026-10-06',
      '2026-10-05',
    ])
  })
})
