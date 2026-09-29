import { apiRequest } from '@/lib/api'

describe('the backend', () => {
  it('answers the health check', async () => {
    await expect(apiRequest('/health')).resolves.toBeDefined()
  })

  it('sends errors in the shape ApiError expects', async () => {
    const error = await apiRequest('/api/auth/me').catch((caught: unknown) => caught)

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })
})
