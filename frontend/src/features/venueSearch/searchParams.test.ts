import {
  filtersFrom,
  readEventToSearchFor,
  readFilters,
  readReplacementSearch,
  readVenueToCheck,
  replacementSearchPath,
  toSearchRequest,
  toSuitabilityRequest,
  venueSearchForEventPath,
  withFilters,
  withVenueToCheck,
} from './searchParams'
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

describe('SCRUM-36 the venue being checked', () => {
  it('reads the venue to check from the URL, or none', () => {
    expect(readVenueToCheck(new URLSearchParams('min_capacity=5&venue=32'))).toBe(32)
    expect(readVenueToCheck(new URLSearchParams('min_capacity=5'))).toBeNull()
  })

  it.each(['abc', '0', '-3', '2.5', ''])('reads no venue from venue=%s', (value) => {
    expect(readVenueToCheck(new URLSearchParams({ venue: value }))).toBeNull()
  })

  it('writes the venue to check into the URL, keeping the filters', () => {
    const next = withVenueToCheck(new URLSearchParams('min_capacity=5&venue=31'), 33)

    expect(next.toString()).toBe('min_capacity=5&venue=33')
  })

  it("checks against the search's needs, its minimum capacity as the attendance", () => {
    const check = toSuitabilityRequest({
      ...FILTERS,
      location: 'Marina',
      required_layout: 'theatre',
      required_facilities: ['projector'],
      required_accessibility: ['step-free access'],
    })

    expect(check).toEqual({
      expected_attendance: 120,
      required_layout: 'theatre',
      required_facilities: ['projector'],
      required_accessibility: ['step-free access'],
    })
  })

  it('checks against any layout when none was chosen', () => {
    expect(toSuitabilityRequest(FILTERS).required_layout).toBeNull()
  })
})

describe('SCRUM-92 a search for a replacement venue', () => {
  const REPLACEMENT = { reference: 'EVR-BOOK0107', arrangementId: 9104, venueId: 31 }

  it('opens the search set to the filters, naming the event, the arrangement and its venue', () => {
    const path = replacementSearchPath(REPLACEMENT, FILTERS)

    expect(path).toBe(
      '/staff/venue-search?event=EVR-BOOK0107&replaces=9104&instead_of=31&date=2026-11-20' +
        '&start=09%3A00&end=17%3A00&min_capacity=120',
    )
  })

  it('reads the replacement back from the URL, beside the filters', () => {
    const params = new URLSearchParams(replacementSearchPath(REPLACEMENT, FILTERS).split('?')[1])

    expect(readReplacementSearch(params)).toEqual(REPLACEMENT)
    expect(readFilters(params)).toEqual(FILTERS)
  })

  it.each([
    'replaces=9104&instead_of=31',
    'event=EVR-BOOK0107&instead_of=31',
    'event=EVR-BOOK0107&replaces=9104',
    'event=EVR-BOOK0107&replaces=abc&instead_of=31',
    'event=EVR-BOOK0107&replaces=9104&instead_of=abc',
  ])('reads no replacement from %s', (query) => {
    expect(readReplacementSearch(new URLSearchParams(query))).toBeNull()
  })
})

describe('SCRUM-90 a search opened from an event', () => {
  const OPENED_PATH = venueSearchForEventPath('EVR-7K2M9QXA')
  const OPENED_PARAMS = new URLSearchParams(OPENED_PATH.split('?')[1])

  it('opens the search naming the event, with no filters until the coordinator searches', () => {
    expect(OPENED_PATH).toBe('/staff/venue-search?for_event=EVR-7K2M9QXA')
    expect(readFilters(OPENED_PARAMS)).toBeNull()
  })

  it('reads the event back from the URL, and keeps it once the filters are added', () => {
    expect(readEventToSearchFor(OPENED_PARAMS)).toBe('EVR-7K2M9QXA')
    expect(readEventToSearchFor(withFilters(OPENED_PARAMS, FILTERS))).toBe('EVR-7K2M9QXA')
  })

  it('reads no event from an ordinary search', () => {
    expect(readEventToSearchFor(new URLSearchParams('date=2026-11-20'))).toBeNull()
  })
})
