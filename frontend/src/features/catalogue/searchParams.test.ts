import { WHEN } from './constants'
import {
  hasCustomRange,
  hasFilters,
  readCatalogueParams,
  withPage,
  withPreset,
  withRangeEnd,
  withSearch,
} from './searchParams'

function params(query: string) {
  return new URLSearchParams(query)
}

describe('SCRUM-52 readCatalogueParams', () => {
  it('reads the catalogue parameters as they are, leaving out empty and unknown ones', () => {
    expect(
      readCatalogueParams(params('q=jazz&when=today&page=2&page_size=5&utm=x&starts_from=')),
    ).toEqual({
      q: 'jazz',
      when: 'today',
      page: '2',
    })
  })
})

describe('SCRUM-52 hasCustomRange and hasFilters', () => {
  it('sees a custom range when either end is set', () => {
    expect(hasCustomRange({ starts_to: '2026-10-20T00:00' })).toBe(true)
    expect(hasCustomRange({ when: WHEN.TODAY })).toBe(false)
  })

  it('counts search, preset and range as filters, but not the page', () => {
    expect(hasFilters({ q: 'jazz' })).toBe(true)
    expect(hasFilters({ when: WHEN.TODAY })).toBe(true)
    expect(hasFilters({ starts_from: '2026-10-20T00:00' })).toBe(true)
    expect(hasFilters({ page: '3' })).toBe(false)
  })
})

describe('SCRUM-52 changing the catalogue URL', () => {
  it('sets the search text and goes back to the first page', () => {
    expect(withSearch(params('when=today&page=3'), 'jazz').toString()).toBe('when=today&q=jazz')
  })

  it('removes the search when it is cleared', () => {
    expect(withSearch(params('q=jazz'), '').toString()).toBe('')
  })

  it('replaces a custom range with a preset', () => {
    const next = withPreset(
      params('starts_from=2026-10-20T00%3A00&starts_to=2026-10-25T00%3A00&page=2'),
      WHEN.THIS_WEEK,
    )

    expect(next.toString()).toBe('when=this_week')
  })

  it('leaves `when` out for Upcoming, the backend default', () => {
    expect(withPreset(params('when=today&q=jazz'), WHEN.UPCOMING).toString()).toBe('q=jazz')
  })

  it('replaces a preset with one end of a custom range', () => {
    expect(withRangeEnd(params('when=today'), 'starts_from', '2026-10-20T09:00').toString()).toBe(
      'starts_from=2026-10-20T09%3A00',
    )
  })

  it('removes a range end that is cleared', () => {
    expect(
      withRangeEnd(params('starts_from=2026-10-20T09%3A00'), 'starts_from', '').toString(),
    ).toBe('')
  })

  it('sets the page, leaving page 1 out', () => {
    expect(withPage(params('q=jazz'), 2).toString()).toBe('q=jazz&page=2')
    expect(withPage(params('q=jazz&page=2'), 1).toString()).toBe('q=jazz')
  })
})
