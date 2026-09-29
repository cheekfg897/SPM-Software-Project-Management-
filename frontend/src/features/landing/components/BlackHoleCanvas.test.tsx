import { render } from '@testing-library/react'

import { drawScene, fitCanvas } from '../blackHole/renderer'
import { stubElementBox, stubPrefersReducedMotion } from '../motionStubs'

import { BlackHoleCanvas } from './BlackHoleCanvas'

// jsdom can't draw, so the renderer is replaced: these tests are about when frames are
// drawn, not what they look like (the e2e tests check the pixels in a real browser).
vi.mock('../blackHole/renderer', () => ({ drawScene: vi.fn(), fitCanvas: vi.fn() }))

// Never read: the renderer that would draw on it is mocked above.
const FAKE_CONTEXT = {} as CanvasRenderingContext2D
const FRAME_ID = 7

function giveCanvasAContext(context: CanvasRenderingContext2D | null) {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => context)
}

function captureAnimationFrames(): FrameRequestCallback[] {
  const frames: FrameRequestCallback[] = []
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    frames.push(callback)
    return FRAME_ID
  })
  return frames
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

describe('BlackHoleCanvas', () => {
  it('is hidden from assistive technology, being decoration', () => {
    giveCanvasAContext(null)

    const { container } = render(<BlackHoleCanvas progress={0} />)

    expect(container.querySelector('canvas')).toHaveAttribute('aria-hidden', 'true')
  })

  it('draws nothing, and does not fail, when the browser gives no 2D context', () => {
    giveCanvasAContext(null)
    const frames = captureAnimationFrames()

    render(<BlackHoleCanvas progress={0} />)

    expect(drawScene).not.toHaveBeenCalled()
    expect(frames).toHaveLength(0)
  })

  it('draws one still frame and never animates when the user prefers reduced motion', () => {
    stubPrefersReducedMotion(true)
    giveCanvasAContext(FAKE_CONTEXT)
    const frames = captureAnimationFrames()

    render(<BlackHoleCanvas progress={0.5} />)

    expect(drawScene).toHaveBeenCalledOnce()
    expect(vi.mocked(drawScene).mock.calls[0]?.[2]).toMatchObject({ seconds: 0 })
    expect(frames).toHaveLength(0)
  })

  it('redraws the still frame at the new size when the window is resized', () => {
    stubPrefersReducedMotion(true)
    giveCanvasAContext(FAKE_CONTEXT)
    render(<BlackHoleCanvas progress={0} />)

    window.dispatchEvent(new Event('resize'))

    expect(fitCanvas).toHaveBeenCalledTimes(2)
    expect(drawScene).toHaveBeenCalledTimes(2)
  })

  it('animates frame after frame at the current scroll progress while on screen', () => {
    stubPrefersReducedMotion(false)
    stubElementBox({ top: 0, height: 800 })
    giveCanvasAContext(FAKE_CONTEXT)
    const frames = captureAnimationFrames()
    const { rerender } = render(<BlackHoleCanvas progress={0} />)
    rerender(<BlackHoleCanvas progress={0.4} />)

    frames[0]?.(2500)

    expect(drawScene).toHaveBeenCalledOnce()
    expect(vi.mocked(drawScene).mock.calls[0]?.[2]).toMatchObject({ progress: 0.4, seconds: 2.5 })
    expect(frames).toHaveLength(2)
  })

  it('skips drawing while scrolled out of view, but keeps the loop going', () => {
    stubPrefersReducedMotion(false)
    stubElementBox({ top: -900, height: 800 })
    giveCanvasAContext(FAKE_CONTEXT)
    const frames = captureAnimationFrames()
    render(<BlackHoleCanvas progress={1} />)

    frames[0]?.(1000)

    expect(drawScene).not.toHaveBeenCalled()
    expect(frames).toHaveLength(2)
  })

  it('stops animating when it leaves the page', () => {
    stubPrefersReducedMotion(false)
    giveCanvasAContext(FAKE_CONTEXT)
    captureAnimationFrames()
    const cancel = vi.spyOn(window, 'cancelAnimationFrame')
    const { unmount } = render(<BlackHoleCanvas progress={0} />)

    unmount()

    expect(cancel).toHaveBeenCalledWith(FRAME_ID)
  })
})
