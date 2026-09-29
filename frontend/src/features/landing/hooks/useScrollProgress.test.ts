import { act, renderHook } from '@testing-library/react'

import { stubElementBox } from '../test/motionStubs'

import { useScrollProgress } from './useScrollProgress'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('useScrollProgress', () => {
  it('stays at 0 until the element is on the page', () => {
    const { result } = renderHook(() => useScrollProgress({ current: null }))

    act(() => {
      window.dispatchEvent(new Event('scroll'))
    })

    expect(result.current).toBe(0)
  })

  it('stays at 0 for an element no taller than the screen, which has nothing to scroll', () => {
    vi.stubGlobal('innerHeight', 800)
    stubElementBox({ top: -100, height: 800 })

    const { result } = renderHook(() => useScrollProgress({ current: document.body }))

    expect(result.current).toBe(0)
  })

  it('measures again when the window is resized', () => {
    vi.stubGlobal('innerHeight', 800)
    stubElementBox({ top: -400, height: 1600 })
    const { result } = renderHook(() => useScrollProgress({ current: document.body }))
    expect(result.current).toBe(0.5)

    vi.stubGlobal('innerHeight', 1200)
    act(() => {
      window.dispatchEvent(new Event('resize'))
    })

    expect(result.current).toBe(1)
  })
})
