import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '@/lib/api'

const MAX_RETRIES = 2

/** Retry outages and network failures, but never a request the backend refused (4xx). */
export function shouldRetry(failureCount: number, error: Error): boolean {
  const wasRefused = error instanceof ApiError && error.isClientError
  return !wasRefused && failureCount < MAX_RETRIES
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry },
      mutations: { retry: false },
    },
  })
}
