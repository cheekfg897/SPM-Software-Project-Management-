import { act, render, screen } from '@testing-library/react'

import { stubIntersectionObserver, stubPrefersReducedMotion } from '../test/motionStubs'

import { Reveal } from './Reveal'

function revealState(): string | null {
  return screen.getByText('Hello').closest('[data-revealed]')?.getAttribute('data-revealed') ?? null
}

afterEach(() => vi.unstubAllGlobals())

describe('Reveal', () => {
  it('stays hidden while below the screen, then shows once it scrolls into view', () => {
    const reportOnScreen = stubIntersectionObserver()
    render(<Reveal>Hello</Reveal>)

    act(() => reportOnScreen(false))
    expect(revealState()).toBe('false')

    act(() => reportOnScreen(true))
    expect(revealState()).toBe('true')
  })

  it('shows at once when the user prefers reduced motion', () => {
    stubIntersectionObserver()
    stubPrefersReducedMotion(true)

    render(<Reveal>Hello</Reveal>)

    expect(revealState()).toBe('true')
  })

  it('shows at once in a browser that cannot watch scrolling', () => {
    vi.stubGlobal('IntersectionObserver', undefined)

    render(<Reveal>Hello</Reveal>)

    expect(revealState()).toBe('true')
  })
})
