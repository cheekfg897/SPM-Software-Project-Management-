import { filtersFrom, readFilters, toSearchRequest, withFilters } from './searchParams'
import type { SearchFilters } from './searchParams'

const FILTERS: SearchFilters = {
  date: '2026-11-20',
  start: '09:00',
  end: '17:00',
  end_date: '',
  min_capacity: '120',
  location: '',
  required_layout: '',
  required_facilities: [],
  required_accessibility: [],
}

function formWith(entries: Record<string, string>): FormData {
  const form = new FormData()
  for (const [name, value] of Object.entries(entries)) {
    form.set(name, value)
  }
  return form
}

describe('SCRUM-35 venue search filters', () => {
  it('reads no filters from a URL that has none', () => {
    expect(readFilters(new URLSearchParams('venue=32'))).toBeNull()
  })

  it('reads every filter from the URL, lists from repeated parameters', () => {
    const params = new URLSearchParams(
      'date=2026-11-20&start=09:00&end=01:00&end_date=2026-11-21&min_capacity=120' +
        '&location=Marina&required_layout=theatre&required_facilities=projector' +
        '&required_facilities=stage&required_accessibility=step-free+access',
    )

    expect(readFilters(params)).toEqual({
      date: '2026-11-20',
      start: '09:00',
      end: '01:00',
      end_date: '2026-11-21',
      min_capacity: '120',
      location: 'Marina',
      required_layout: 'theatre',
      required_facilities: ['projector', 'stage'],
      required_accessibility: ['step-free access'],
    })
  })

  it('reads one filter alone as a search, the rest left empty', () => {
    expect(readFilters(new URLSearchParams('location=Sentosa'))).toEqual({
      ...FILTERS,
      date: '',
      start: '',
      end: '',
      min_capacity: '',
      location: 'Sentosa',
    })
  })

  it('takes one requirement per line from the form, dropping empty lines and outer spaces', () => {
    const filters = filtersFrom(
      formWith({
        date: '2026-11-20',
        min_capacity: '120',
        required_facilities: ' projector \r\n\r\n  \nstage',
        required_accessibility: '',
      }),
    )

    expect(filters).toEqual({
      ...FILTERS,
      start: '',
      end: '',
      required_facilities: ['projector', 'stage'],
      required_accessibility: [],
    })
  })

  it('writes the filters into the URL, leaving out empty ones and keeping the venue checked', () => {
    const current = new URLSearchParams('venue=32&location=Old&required_facilities=old')

    const next = withFilters(current, {
      ...FILTERS,
      required_facilities: ['projector', 'stage'],
    })

    expect(next.toString()).toBe(
      'venue=32&date=2026-11-20&start=09%3A00&end=17%3A00&min_capacity=120' +
        '&required_facilities=projector&required_facilities=stage',
    )
  })
})

describe('SCRUM-35 the search sent to the backend', () => {
  it('sends the period in business time, ending on the start date when no end date is given', () => {
    expect(toSearchRequest(FILTERS)).toEqual({
      start_time: '2026-11-20T09:00:00+08:00',
      end_time: '2026-11-20T17:00:00+08:00',
      min_capacity: 120,
      location: null,
      required_layout: null,
      required_facilities: [],
      required_accessibility: [],
    })
  })

  it('ends on the end date when one is given, and sends every requirement', () => {
    const search = toSearchRequest({
      ...FILTERS,
      end: '01:00',
      end_date: '2026-11-21',
      location: 'Marina',
      required_layout: 'banquet',
      required_facilities: ['projector'],
      required_accessibility: ['step-free access'],
    })

    expect(search).toMatchObject({
      end_time: '2026-11-21T01:00:00+08:00',
      location: 'Marina',
      required_layout: 'banquet',
      required_facilities: ['projector'],
      required_accessibility: ['step-free access'],
    })
  })
})
