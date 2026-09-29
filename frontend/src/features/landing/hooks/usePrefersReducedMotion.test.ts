import { act, renderHook } from '@testing-library/react'

import { stubPrefersReducedMotion } from '../motionStubs'

import { usePrefersReducedMotion } from './usePrefersReducedMotion'

afterEach(() => vi.unstubAllGlobals())

describe('usePrefersReducedMotion', () => {
  it('follows the system setting', () => {
    stubPrefersReducedMotion(true)

    const { result } = renderHook(() => usePrefersReducedMotion())

    expect(result.current).toBe(true)
  })

  it('updates when the user changes the setting', () => {
    const changeSetting = stubPrefersReducedMotion(false)
    const { result } = renderHook(() => usePrefersReducedMotion())

    act(() => changeSetting(true))

    expect(result.current).toBe(true)
  })

  it('allows motion in a browser that cannot say', () => {
    vi.stubGlobal('matchMedia', undefined)

    const { result } = renderHook(() => usePrefersReducedMotion())

    expect(result.current).toBe(false)
  })
})
