import { ApiError } from '@/lib/api'

import { createQueryClient, shouldRetry } from './queryClient'

describe('shouldRetry', () => {
  it('never retries a request the backend refused', () => {
    expect(shouldRetry(0, new ApiError(404, 'not_found', 'Gone.'))).toBe(false)
  })

  it('retries server and network failures twice', () => {
    const outage = new ApiError(503, 'unavailable', 'Down.')

    expect(shouldRetry(0, outage)).toBe(true)
    expect(shouldRetry(1, outage)).toBe(true)
    expect(shouldRetry(2, outage)).toBe(false)
    expect(shouldRetry(0, new Error('boom'))).toBe(true)
  })
})

describe('createQueryClient', () => {
  it('retries queries by shouldRetry and never retries a mutation', () => {
    const options = createQueryClient().getDefaultOptions()

    expect(options.queries?.retry).toBe(shouldRetry)
    expect(options.mutations?.retry).toBe(false)
  })
})
