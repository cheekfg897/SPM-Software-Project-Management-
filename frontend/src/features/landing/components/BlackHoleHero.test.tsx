import { act, screen } from '@testing-library/react'

import { ROUTES } from '@/config/routes'
import { renderWithProviders } from '@/test/render'

import { stubElementBox, stubPrefersReducedMotion } from '../test/motionStubs'

import { BlackHoleHero } from './BlackHoleHero'

vi.mock('../blackHole/renderer', () => ({ drawScene: vi.fn(), fitCanvas: vi.fn() }))

const VIEWPORT_HEIGHT = 1000
const HERO_HEIGHT = 2000

function heroSection(): HTMLElement {
  return screen.getByRole('region', { name: 'Every event finds its orbit.' })
}

function scrollTo(top: number) {
  stubElementBox({ top, height: HERO_HEIGHT })
  act(() => {
    window.dispatchEvent(new Event('scroll'))
  })
}

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => null)
  vi.stubGlobal('innerHeight', VIEWPORT_HEIGHT)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('BlackHoleHero', () => {
  it('says what ConnectSphere is and offers both ways in', () => {
    renderWithProviders(<BlackHoleHero />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Every event finds its orbit.',
    )
    expect(screen.getByRole('link', { name: 'Browse events' })).toHaveAttribute(
      'href',
      ROUTES.EVENTS,
    )
    expect(screen.getByRole('link', { name: 'Host an event' })).toHaveAttribute(
      'href',
      ROUTES.SIGN_UP,
    )
  })

  it('tracks how far the visitor has scrolled through it', () => {
    renderWithProviders(<BlackHoleHero />)

    // The hero is 2000px tall on a 1000px screen, so it scrolls through 1000px in all.
    scrollTo(-250)
    expect(heroSection()).toHaveAttribute('data-scroll-progress', '0.25')

    scrollTo(-3000)
    expect(heroSection()).toHaveAttribute('data-scroll-progress', '1.00')
  })

  it('fades the words out and hides them once the visitor scrolls on', () => {
    renderWithProviders(<BlackHoleHero />)
    const copy = screen.getByRole('heading', { level: 1 }).parentElement

    expect(copy).toHaveStyle({ opacity: '1', visibility: 'visible' })

    scrollTo(-600)

    expect(copy).toHaveStyle({ opacity: '0', visibility: 'hidden' })
  })

  it('keeps still when the user prefers reduced motion', () => {
    stubPrefersReducedMotion(true)
    renderWithProviders(<BlackHoleHero />)

    scrollTo(-500)

    expect(heroSection()).toHaveAttribute('data-scroll-progress', '0.00')
    expect(screen.getByRole('heading', { level: 1 }).parentElement).toHaveStyle({ opacity: '1' })
  })

  it('stops listening to the scroll when it leaves the page', () => {
    const removeListener = vi.spyOn(window, 'removeEventListener')
    const { unmount } = renderWithProviders(<BlackHoleHero />)

    unmount()

    expect(removeListener).toHaveBeenCalledWith('scroll', expect.any(Function))
  })
})
